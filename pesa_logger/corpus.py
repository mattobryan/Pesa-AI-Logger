"""Parser corpus loading and validation utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pesa_logger.parser import parse_sms


@dataclass
class CorpusValidationResult:
    total: int
    expected_parsable: int
    parsed_ok: int
    parsed_fail: int
    field_mismatches: int
    success_rate: float
    failures: List[dict]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "expected_parsable": self.expected_parsable,
            "parsed_ok": self.parsed_ok,
            "parsed_fail": self.parsed_fail,
            "field_mismatches": self.field_mismatches,
            "success_rate": self.success_rate,
            "failures": self.failures,
        }


def load_corpus(path: str) -> List[dict]:
    """Load corpus from JSONL path."""
    corpus_path = Path(path)
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {path}")

    entries: List[dict] = []
    with corpus_path.open("r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc
            if "sms" not in payload:
                raise ValueError(f"Missing 'sms' field at line {line_no}")
            payload["_line_no"] = line_no
            entries.append(payload)
    return entries


def _extract_expected(entry: dict) -> Dict[str, Any]:
    expected = entry.get("expected", {})
    if not isinstance(expected, dict):
        raise ValueError("expected field must be an object when provided")
    return expected


def validate_corpus(
    path: str,
    min_success_rate: float = 0.98,
) -> dict:
    """Validate parser behavior against corpus expectations."""
    if not 0 <= min_success_rate <= 1:
        raise ValueError("min_success_rate must be between 0 and 1")

    entries = load_corpus(path)
    expected_parsable = 0
    parsed_ok = 0
    parsed_fail = 0
    field_mismatches = 0
    failures: List[dict] = []

    for entry in entries:
        sms = entry["sms"]
        expect_parse = bool(entry.get("expect_parse", True))
        expected = _extract_expected(entry)
        tx = parse_sms(sms)

        if expect_parse:
            expected_parsable += 1
            if tx is None:
                parsed_fail += 1
                failures.append(
                    {
                        "line": entry["_line_no"],
                        "reason": "parse_failed",
                        "sms": sms,
                    }
                )
                continue

            tx_dict = tx.to_dict()
            mismatch = {}
            for key, expected_value in expected.items():
                if tx_dict.get(key) != expected_value:
                    mismatch[key] = {
                        "expected": expected_value,
                        "actual": tx_dict.get(key),
                    }

            if mismatch:
                field_mismatches += 1
                failures.append(
                    {
                        "line": entry["_line_no"],
                        "reason": "field_mismatch",
                        "mismatch": mismatch,
                        "sms": sms,
                    }
                )
            else:
                parsed_ok += 1
        else:
            if tx is not None:
                field_mismatches += 1
                failures.append(
                    {
                        "line": entry["_line_no"],
                        "reason": "unexpected_parse",
                        "actual_type": tx.type,
                        "sms": sms,
                    }
                )

    denom = expected_parsable if expected_parsable > 0 else max(len(entries), 1)
    success_rate = parsed_ok / denom
    passed_gate = success_rate >= min_success_rate and parsed_fail == 0 and field_mismatches == 0

    result = CorpusValidationResult(
        total=len(entries),
        expected_parsable=expected_parsable,
        parsed_ok=parsed_ok,
        parsed_fail=parsed_fail,
        field_mismatches=field_mismatches,
        success_rate=success_rate,
        failures=failures,
    )
    payload = result.to_dict()
    payload["min_success_rate"] = min_success_rate
    payload["passed_gate"] = passed_gate
    return payload
