"""Provider-agnostic AI engine for Pesa AI Logger.

Supports OpenAI, Anthropic (Claude), Ollama (local LLMs), and a Stub
provider for offline/test use. The active provider is controlled entirely
via environment variables — no code changes needed to switch.

Environment variables
---------------------
AI_PROVIDER        : openai | anthropic | ollama | stub  (default: stub)
OPENAI_API_KEY     : required when AI_PROVIDER=openai
OPENAI_MODEL       : default gpt-4o-mini
ANTHROPIC_API_KEY  : required when AI_PROVIDER=anthropic
ANTHROPIC_MODEL    : default claude-haiku-4-5-20251001
OLLAMA_BASE_URL    : default http://localhost:11434
OLLAMA_MODEL       : default llama3
AI_MAX_TOKENS      : default 512
AI_TEMPERATURE     : default 0.3
AI_TIMEOUT_SECONDS : default 30
AI_MAX_RETRIES     : default 2
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Provider enum ────────────────────────────────────────────────────────────

class AIProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    STUB = "stub"


# ─── Response dataclass ───────────────────────────────────────────────────────

@dataclass
class AIResponse:
    """Structured response from any AI provider."""
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "cached": self.cached,
            "error": self.error,
        }


# ─── Config ───────────────────────────────────────────────────────────────────

@dataclass
class AIConfig:
    provider: AIProvider = AIProvider.STUB
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    max_tokens: int = 512
    temperature: float = 0.3
    timeout_seconds: int = 30
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "AIConfig":
        provider_str = os.environ.get("AI_PROVIDER", "stub").lower().strip()
        try:
            provider = AIProvider(provider_str)
        except ValueError:
            logger.warning("Unknown AI_PROVIDER=%r — falling back to stub", provider_str)
            provider = AIProvider.STUB

        return cls(
            provider=provider,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3"),
            max_tokens=int(os.environ.get("AI_MAX_TOKENS", 512)),
            temperature=float(os.environ.get("AI_TEMPERATURE", 0.3)),
            timeout_seconds=int(os.environ.get("AI_TIMEOUT_SECONDS", 30)),
            max_retries=int(os.environ.get("AI_MAX_RETRIES", 2)),
        )


# ─── Simple in-process response cache ─────────────────────────────────────────

class _ResponseCache:
    """Thread-safe LRU-style prompt → response cache (max 256 entries)."""

    _MAX = 256

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def _key(self, system: str, user: str) -> str:
        import hashlib
        raw = f"{system}|||{user}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, system: str, user: str) -> Optional[str]:
        return self._store.get(self._key(system, user))

    def set(self, system: str, user: str, value: str) -> None:
        if len(self._store) >= self._MAX:
            # evict oldest (first inserted)
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[self._key(system, user)] = value

    def clear(self) -> None:
        self._store.clear()


# ─── AIEngine ─────────────────────────────────────────────────────────────────

class AIEngine:
    """
    Unified interface to multiple AI providers.

    Usage
    -----
    engine = AIEngine.from_env()
    response = engine.complete(system="You are...", user="What is...")
    print(response.content)
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        self.config = config or AIConfig.from_env()
        self._cache = _ResponseCache()

    @classmethod
    def from_env(cls) -> "AIEngine":
        return cls(config=AIConfig.from_env())

    @property
    def provider_name(self) -> str:
        return self.config.provider.value

    @property
    def model_name(self) -> str:
        cfg = self.config
        if cfg.provider == AIProvider.OPENAI:
            return cfg.openai_model
        if cfg.provider == AIProvider.ANTHROPIC:
            return cfg.anthropic_model
        if cfg.provider == AIProvider.OLLAMA:
            return cfg.ollama_model
        return "stub"

    def complete(
        self,
        user: str,
        system: str = "",
        use_cache: bool = True,
        json_mode: bool = False,
    ) -> AIResponse:
        """
        Send a completion request.

        Parameters
        ----------
        user       : The user-facing prompt.
        system     : Optional system/instruction prompt.
        use_cache  : Return cached response if available (default True).
        json_mode  : Hint to the model to return valid JSON only.
        """
        # Cache check
        if use_cache:
            cached = self._cache.get(system, user)
            if cached is not None:
                return AIResponse(
                    content=cached,
                    provider=self.provider_name,
                    model=self.model_name,
                    cached=True,
                )

        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= self.config.max_retries:
            try:
                t0 = time.monotonic()
                response = self._dispatch(user=user, system=system, json_mode=json_mode)
                latency = (time.monotonic() - t0) * 1000
                response.latency_ms = latency

                if use_cache and response.success:
                    self._cache.set(system, user, response.content)

                return response

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempt += 1
                if attempt <= self.config.max_retries:
                    wait = 2 ** attempt  # exponential backoff: 2s, 4s
                    logger.warning(
                        "AI request failed (attempt %d/%d): %s — retrying in %ds",
                        attempt, self.config.max_retries, exc, wait,
                    )
                    time.sleep(wait)

        logger.error("AI request failed after %d retries: %s", self.config.max_retries, last_error)
        return AIResponse(
            content="",
            provider=self.provider_name,
            model=self.model_name,
            error=str(last_error),
        )

    def complete_json(self, user: str, system: str = "") -> AIResponse:
        """Convenience wrapper that sets json_mode=True."""
        return self.complete(user=user, system=system, json_mode=True, use_cache=False)

    def clear_cache(self) -> None:
        self._cache.clear()

    # ── Private dispatch ──────────────────────────────────────────────────────

    def _dispatch(self, user: str, system: str, json_mode: bool) -> AIResponse:
        p = self.config.provider
        if p == AIProvider.OPENAI:
            return self._call_openai(user, system, json_mode)
        if p == AIProvider.ANTHROPIC:
            return self._call_anthropic(user, system, json_mode)
        if p == AIProvider.OLLAMA:
            return self._call_ollama(user, system, json_mode)
        return self._call_stub(user, system)

    def _call_openai(self, user: str, system: str, json_mode: bool) -> AIResponse:
        try:
            import openai
        except ImportError as exc:
            raise ImportError("pip install openai") from exc

        client = openai.OpenAI(
            api_key=self.config.openai_api_key,
            timeout=self.config.timeout_seconds,
        )
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        kwargs: Dict[str, Any] = dict(
            model=self.config.openai_model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        usage = resp.usage

        return AIResponse(
            content=content.strip(),
            provider="openai",
            model=self.config.openai_model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
        )

    def _call_anthropic(self, user: str, system: str, json_mode: bool) -> AIResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc

        client = anthropic.Anthropic(
            api_key=self.config.anthropic_api_key,
            timeout=self.config.timeout_seconds,
        )

        effective_system = system
        if json_mode and effective_system:
            effective_system += "\n\nRespond ONLY with valid JSON. No explanation, no markdown."
        elif json_mode:
            effective_system = "Respond ONLY with valid JSON. No explanation, no markdown."

        resp = client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=self.config.max_tokens,
            system=effective_system or "You are a helpful financial assistant.",
            messages=[{"role": "user", "content": user}],
        )
        content = resp.content[0].text if resp.content else ""

        return AIResponse(
            content=content.strip(),
            provider="anthropic",
            model=self.config.anthropic_model,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
        )

    def _call_ollama(self, user: str, system: str, json_mode: bool) -> AIResponse:
        import urllib.request
        import json as _json

        payload: Dict[str, Any] = {
            "model": self.config.ollama_model,
            "prompt": f"{system}\n\n{user}".strip() if system else user,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        url = f"{self.config.ollama_base_url.rstrip('/')}/api/generate"
        data = _json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
            body = _json.loads(resp.read().decode())

        content = body.get("response", "")
        return AIResponse(
            content=content.strip(),
            provider="ollama",
            model=self.config.ollama_model,
            prompt_tokens=body.get("prompt_eval_count", 0),
            completion_tokens=body.get("eval_count", 0),
        )

    def _call_stub(self, user: str, system: str) -> AIResponse:  # noqa: ARG002
        """Returns a deterministic stub response for testing/offline use."""
        stub_text = (
            "AI provider not configured (AI_PROVIDER=stub). "
            "Set AI_PROVIDER and the corresponding API key to enable AI insights."
        )
        return AIResponse(
            content=stub_text,
            provider="stub",
            model="stub",
        )


# ─── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[AIEngine] = None


def get_engine() -> AIEngine:
    """Return the module-level singleton AIEngine, initialised from env."""
    global _engine
    if _engine is None:
        _engine = AIEngine.from_env()
    return _engine


def reset_engine() -> None:
    """Reset the singleton (useful for tests / config changes)."""
    global _engine
    _engine = None