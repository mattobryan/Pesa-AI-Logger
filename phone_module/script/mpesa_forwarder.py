#!/usr/bin/env python3
"""Termux SMS forwarder for MPESA pilot ingestion.

Workflow:
1) Poll inbox SMS via `termux-sms-list`.
2) Filter MPESA-like messages.
3) Queue and retry POST delivery to `/sms`.
4) Persist state locally so restarts are safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_CONFIG = {
    "endpoint_url": "http://127.0.0.1:5000/sms",
    "source": "android-termux",
    "api_key": "",
    "required_terms": ["m-pesa", "confirmed", "ksh"],
    "poll_interval_seconds": 30,
    "fetch_limit": 50,
    "backfill_page_size": 200,
    "backfill_max_pages": 100,
    "max_processed_keys": 5000,
    "retry_base_seconds": 15,
    "retry_max_seconds": 900,
    "max_retries": 0,
    "request_timeout_seconds": 15,
    "success_status_codes": [200, 201, 422],
}

ENV_CONFIG_PATH = "MPESA_FORWARDER_CONFIG"
ENV_STATE_PATH = "MPESA_FORWARDER_STATE"
ENV_LOG_PATH = "MPESA_FORWARDER_LOG"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(tzinfo=None).isoformat()


def parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(default)


def load_config(config_path: Path) -> dict:
    raw = load_json(config_path, DEFAULT_CONFIG)
    config = dict(DEFAULT_CONFIG)
    config.update(raw)
    return config


def resolve_runtime_paths(
    config_arg: Optional[str],
    state_arg: Optional[str],
    log_arg: Optional[str],
    base_dir: Optional[Path] = None,
) -> Tuple[Path, Path, Path]:
    """Resolve config/state/log paths with CLI -> env -> defaults precedence.

    Defaults are anchored to:
    - script directory when config is defaulted
    - config directory when config path is explicitly set (CLI/env)
    """
    script_dir = (base_dir or Path(__file__).resolve().parent).resolve()
    config_candidate = config_arg or os.environ.get(ENV_CONFIG_PATH)
    if config_candidate:
        config_path = Path(config_candidate).expanduser().resolve()
    else:
        config_path = (script_dir / "config.json").resolve()

    default_root = config_path.parent

    state_candidate = state_arg or os.environ.get(ENV_STATE_PATH)
    if state_candidate:
        state_path = Path(state_candidate).expanduser().resolve()
    else:
        state_path = (default_root / "runtime" / "state.json").resolve()

    log_candidate = log_arg or os.environ.get(ENV_LOG_PATH)
    if log_candidate:
        log_path = Path(log_candidate).expanduser().resolve()
    else:
        log_path = (default_root / "runtime" / "forwarder.log").resolve()

    return config_path, state_path, log_path


def default_state() -> dict:
    return {
        "processed_keys": [],
        "queue": [],
        "stats": {
            "forwarded": 0,
            "failed_attempts": 0,
            "dropped": 0,
            "last_success_utc": None,
            "last_failure_utc": None,
        },
        "last_poll_utc": None,
    }


def extract_sms_body(message: dict) -> str:
    for key in ("body", "message", "text"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def extract_sender(message: dict) -> Optional[str]:
    for key in ("number", "address", "sender"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def extract_sim_slot(message: dict) -> Optional[str]:
    for key in (
        "subscription_id",
        "subscriptionId",
        "sub_id",
        "sim_slot",
        "slot",
        "simId",
    ):
        value = message.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def parse_sms_timestamp_utc(message: dict) -> Optional[str]:
    for key in ("date", "received", "date_sent", "timestamp"):
        value = message.get(key)
        if value is None:
            continue

        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1_000_000_000_000:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None).isoformat()

        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            if text.isdigit():
                ts_int = int(text)
                if ts_int > 1_000_000_000_000:
                    ts_int = ts_int // 1000
                return datetime.fromtimestamp(ts_int, tz=timezone.utc).replace(tzinfo=None).isoformat()
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat()

    return None


def message_identity_key(message: dict) -> str:
    raw_id = message.get("_id") or message.get("id")
    sender = extract_sender(message) or ""
    body = extract_sms_body(message)
    stamp = parse_sms_timestamp_utc(message) or ""
    base = f"{raw_id}|{sender}|{stamp}|{body}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def matches_required_terms(text: str, required_terms: List[str]) -> bool:
    lower = text.lower()
    for term in required_terms:
        if term.lower() not in lower:
            return False
    return True


def _parse_sms_list_payload(stdout: str) -> List[dict]:
    payload = json.loads(stdout)
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return [p for p in payload["messages"] if isinstance(p, dict)]
    raise RuntimeError("Unexpected output from termux-sms-list; expected JSON list")


def _run_termux_sms_list(limit: int, offset: Optional[int]) -> List[dict]:
    command = [
        "termux-sms-list",
        "-t",
        "inbox",
        "-l",
        str(max(1, int(limit))),
    ]
    if offset is not None and offset > 0:
        command.extend(["-o", str(offset)])

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if offset is not None and offset > 0:
            lowered = stderr.lower()
            if any(
                marker in lowered
                for marker in ("unknown option", "invalid option", "unrecognized", "usage:")
            ):
                raise RuntimeError("termux-sms-list offset_not_supported")
        raise RuntimeError(f"termux-sms-list failed: {stderr or 'unknown error'}")

    stdout = (result.stdout or "").strip()
    if not stdout:
        return []
    return _parse_sms_list_payload(stdout)


def _dedupe_messages(messages: List[dict]) -> List[dict]:
    seen: set = set()
    deduped: List[dict] = []
    for message in messages:
        key = message_identity_key(message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(message)
    return deduped


def _fetch_inbox_sms_pages(
    fetch_limit: int,
    backfill: bool,
    page_size: int,
    max_pages: int,
) -> List[dict]:
    if not backfill:
        return _run_termux_sms_list(limit=fetch_limit, offset=None)

    page_size = max(1, int(page_size))
    max_pages = max(1, int(max_pages))
    all_messages: List[dict] = []

    first_page = _run_termux_sms_list(limit=page_size, offset=None)
    all_messages.extend(first_page)
    if len(first_page) < page_size:
        return _dedupe_messages(all_messages)

    for page in range(1, max_pages):
        offset = page * page_size
        try:
            batch = _run_termux_sms_list(limit=page_size, offset=offset)
        except RuntimeError as exc:
            if "offset_not_supported" not in str(exc):
                raise
            # Fallback if this Termux API build cannot page by offset.
            fallback_limit = page_size * max_pages
            all_messages.extend(_run_termux_sms_list(limit=fallback_limit, offset=None))
            return _dedupe_messages(all_messages)

        if not batch:
            break
        all_messages.extend(batch)
        if len(batch) < page_size:
            break

    return _dedupe_messages(all_messages)


def fetch_inbox_sms(
    fetch_limit: int,
    backfill: bool = False,
    page_size: Optional[int] = None,
    max_pages: Optional[int] = None,
) -> List[dict]:
    page = int(page_size or fetch_limit)
    pages = int(max_pages or 1)
    return _fetch_inbox_sms_pages(
        fetch_limit=fetch_limit,
        backfill=backfill,
        page_size=page,
        max_pages=pages,
    )


def build_payload(item: dict, source: str) -> dict:
    return {
        "sms": item["sms"],
        "source": source,
        "meta": {
            "key": item["key"],
            "sender": item.get("sender"),
            "sim_slot": item.get("sim_slot"),
            "sms_timestamp_utc": item.get("sms_timestamp_utc"),
            "enqueued_at_utc": item.get("enqueued_at_utc"),
        },
    }


def post_sms(
    endpoint_url: str,
    payload: dict,
    timeout_seconds: int,
    api_key: str = "",
) -> Tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    request = Request(endpoint_url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.getcode()), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def _parse_status_codes(raw: List[Any]) -> List[int]:
    status_codes = []
    for item in raw:
        try:
            status_codes.append(int(item))
        except (TypeError, ValueError):
            continue
    return status_codes or [200, 201, 422]


def enqueue_new_messages(messages: List[dict], state: dict, config: dict) -> int:
    queue: List[dict] = state["queue"]
    processed: List[str] = state["processed_keys"]
    processed_set = set(processed)
    required_terms = config["required_terms"]
    count = 0

    ordered = sorted(
        messages,
        key=lambda msg: parse_sms_timestamp_utc(msg) or "",
    )
    now_iso = utc_now_iso()

    for message in ordered:
        sms_text = extract_sms_body(message)
        if not sms_text:
            continue
        if not matches_required_terms(sms_text, required_terms):
            continue

        key = message_identity_key(message)
        if key in processed_set:
            continue

        item = {
            "key": key,
            "sms": sms_text,
            "sender": extract_sender(message),
            "sim_slot": extract_sim_slot(message),
            "sms_timestamp_utc": parse_sms_timestamp_utc(message),
            "enqueued_at_utc": now_iso,
            "retries": 0,
            "last_error": None,
            "next_attempt_utc": now_iso,
        }
        queue.append(item)
        processed.append(key)
        processed_set.add(key)
        count += 1

    max_processed_keys = int(config["max_processed_keys"])
    if max_processed_keys > 0 and len(processed) > max_processed_keys:
        trim = len(processed) - max_processed_keys
        del processed[:trim]

    return count


def process_queue(state: dict, config: dict) -> dict:
    queue: List[dict] = state["queue"]
    remaining: List[dict] = []
    now = utc_now()
    stats = state["stats"]
    success_statuses = set(_parse_status_codes(config["success_status_codes"]))

    for item in queue:
        due_at_text = item.get("next_attempt_utc")
        if due_at_text:
            due_at = parse_iso_utc(due_at_text)
            if due_at > now:
                remaining.append(item)
                continue

        payload = build_payload(item, config["source"])
        try:
            status, _body = post_sms(
                endpoint_url=config["endpoint_url"],
                payload=payload,
                timeout_seconds=int(config["request_timeout_seconds"]),
                api_key=str(config.get("api_key") or ""),
            )
            if status in success_statuses:
                stats["forwarded"] += 1
                stats["last_success_utc"] = utc_now_iso()
                continue

            item["last_error"] = f"http_status_{status}"
        except Exception as exc:  # noqa: BLE001
            item["last_error"] = str(exc)

        stats["failed_attempts"] += 1
        stats["last_failure_utc"] = utc_now_iso()
        item["retries"] = int(item.get("retries", 0)) + 1

        max_retries = int(config.get("max_retries", 0))
        if max_retries > 0 and item["retries"] >= max_retries:
            stats["dropped"] += 1
            continue

        base = int(config["retry_base_seconds"])
        max_delay = int(config["retry_max_seconds"])
        delay = min(max_delay, base * (2 ** max(0, item["retries"] - 1)))
        next_attempt = utc_now() + timedelta(seconds=delay)
        item["next_attempt_utc"] = next_attempt.replace(tzinfo=None).isoformat()
        remaining.append(item)

    state["queue"] = remaining
    return state


@dataclass
class ForwarderRuntime:
    config_path: Path
    state_path: Path
    log_path: Path

    def log(self, message: str) -> None:
        line = f"{utc_now_iso()} {message}"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)


def run_cycle(
    runtime: ForwarderRuntime,
    dry_run: bool = False,
    backfill: bool = False,
    backfill_page_size: Optional[int] = None,
    backfill_max_pages: Optional[int] = None,
) -> dict:
    config = load_config(runtime.config_path)
    state = load_json(runtime.state_path, default_state())

    try:
        fetch_limit = int(config["fetch_limit"])
        page_size = int(backfill_page_size or config.get("backfill_page_size") or fetch_limit)
        max_pages = int(backfill_max_pages or config.get("backfill_max_pages") or 1)
        messages = fetch_inbox_sms(
            fetch_limit=fetch_limit,
            backfill=backfill,
            page_size=page_size,
            max_pages=max_pages,
        )
        enqueued = enqueue_new_messages(messages, state, config)
        runtime.log(
            f"polled={len(messages)} backfill={str(backfill).lower()} "
            f"enqueued={enqueued} queue={len(state['queue'])}"
        )
    except Exception as exc:  # noqa: BLE001
        runtime.log(f"poll_error={exc}")

    if dry_run:
        runtime.log("dry_run=true; queue not delivered")
    else:
        before = len(state["queue"])
        state = process_queue(state, config)
        after = len(state["queue"])
        runtime.log(
            f"delivery_attempted={before} remaining_queue={after} "
            f"forwarded={state['stats']['forwarded']}"
        )

    state["last_poll_utc"] = utc_now_iso()
    atomic_write_json(runtime.state_path, state)
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Termux MPESA SMS forwarder")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to config file. "
            "Default: ./config.json in script dir "
            f"(env: {ENV_CONFIG_PATH})"
        ),
    )
    parser.add_argument(
        "--state",
        default=None,
        help=(
            "Path to state file. "
            "Default: ./runtime/state.json in script dir "
            f"(env: {ENV_STATE_PATH})"
        ),
    )
    parser.add_argument(
        "--log",
        default=None,
        help=(
            "Path to log file. "
            "Default: ./runtime/forwarder.log in script dir "
            f"(env: {ENV_LOG_PATH})"
        ),
    )
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Poll/enqueue without POST delivery")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Run in historical backfill mode using SMS paging before normal polling",
    )
    parser.add_argument(
        "--backfill-page-size",
        type=int,
        default=None,
        help="Backfill page size override (defaults to config backfill_page_size)",
    )
    parser.add_argument(
        "--backfill-max-pages",
        type=int,
        default=None,
        help="Backfill max pages override (defaults to config backfill_max_pages)",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Create config file from defaults if missing and exit",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print effective runtime config and paths, then exit",
    )
    return parser


def maybe_init_config(config_path: Path) -> bool:
    if config_path.exists():
        return False
    atomic_write_json(config_path, DEFAULT_CONFIG)
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config_path, state_path, log_path = resolve_runtime_paths(
        config_arg=args.config,
        state_arg=args.state,
        log_arg=args.log,
    )
    runtime = ForwarderRuntime(
        config_path=config_path,
        state_path=state_path,
        log_path=log_path,
    )

    if args.init_config:
        created = maybe_init_config(config_path)
        if created:
            print(f"Created config at {config_path}")
        else:
            print(f"Config already exists at {config_path}")
        return 0

    if not config_path.exists():
        print(
            f"Missing config at {config_path}. "
            f"Run with --init-config first.",
            file=sys.stderr,
        )
        return 1

    config = load_config(config_path)
    runtime.log(f"using_config_path={runtime.config_path}")
    runtime.log(f"using_endpoint_url={config.get('endpoint_url')}")
    if not str(config.get("endpoint_url", "")).strip().endswith("/sms"):
        runtime.log("warning endpoint_url does_not_end_with_/sms")

    if args.print_config:
        payload = dict(config)
        payload["_config_path"] = str(runtime.config_path)
        payload["_state_path"] = str(runtime.state_path)
        payload["_log_path"] = str(runtime.log_path)
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0

    if args.once:
        run_cycle(
            runtime,
            dry_run=args.dry_run,
            backfill=args.backfill,
            backfill_page_size=args.backfill_page_size,
            backfill_max_pages=args.backfill_max_pages,
        )
        return 0

    interval = max(5, int(config["poll_interval_seconds"]))
    runtime.log(f"starting_forwarder poll_interval_seconds={interval}")
    while True:
        run_cycle(
            runtime,
            dry_run=args.dry_run,
            backfill=False,
        )
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
