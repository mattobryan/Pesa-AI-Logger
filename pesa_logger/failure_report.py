"""Failed-message classification and reporting helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pesa_logger.database import list_inbox_sms


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _contains_all(text: str, terms: List[str]) -> bool:
    return all(term in text for term in terms)


def classify_failed_message(raw_text: str) -> Dict[str, object]:
    """Classify a failed SMS into a deterministic family."""
    text = " ".join((raw_text or "").strip().lower().split())

    if _contains_all(text, ["fuliza m-pesa amount is ksh", "interest charged"]):
        return {
            "class": "fuliza_drawdown_notice",
            "is_receipt": True,
            "description": "Fuliza drawdown notice (loan + interest metadata).",
        }

    if _contains_all(text, ["from your m-pesa has been used to", "fuliza m-pesa"]):
        return {
            "class": "fuliza_repayment_receipt",
            "is_receipt": True,
            "description": "Fuliza repayment receipt (partial/full pay notice).",
        }

    if _contains_all(text, ["you bought ksh", "airtime"]):
        return {
            "class": "airtime_purchase_receipt",
            "is_receipt": True,
            "description": "Airtime purchase receipt.",
        }

    if _contains_all(text, ["transaction", "has been received"]):
        return {
            "class": "merchant_ack_receipt",
            "is_receipt": True,
            "description": "Merchant/paybill acknowledgement receipt.",
        }

    return {
        "class": "unknown_unparsed",
        "is_receipt": False,
        "description": "No known failed-message family match.",
    }


def _trim_sample(raw_text: str, max_chars: int = 220) -> str:
    compact = " ".join((raw_text or "").strip().split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def build_failed_report(
    db_path: str,
    limit: int = 5000,
    sim_slot: Optional[str] = None,
    sample_size: int = 3,
) -> Dict[str, object]:
    """Return grouped classification report for failed inbox messages."""
    rows = list_inbox_sms(
        db_path=db_path,
        limit=limit,
        oldest_first=False,
        parse_status="failed",
        sim_slot=sim_slot,
    )

    class_stats: Dict[str, Dict[str, object]] = {}
    sim_counts: Dict[str, int] = {}

    for row in rows:
        classification = classify_failed_message(str(row.get("raw_text") or ""))
        class_name = str(classification["class"])
        if class_name not in class_stats:
            class_stats[class_name] = {
                "class": class_name,
                "is_receipt": bool(classification["is_receipt"]),
                "description": str(classification["description"]),
                "count": 0,
                "sample_rows": [],
            }
        class_stats[class_name]["count"] = int(class_stats[class_name]["count"]) + 1

        samples = class_stats[class_name]["sample_rows"]
        if isinstance(samples, list) and len(samples) < sample_size:
            samples.append(
                {
                    "id": row.get("id"),
                    "received_at_utc": row.get("received_at_utc"),
                    "sim_slot": row.get("sim_slot"),
                    "raw_text": _trim_sample(str(row.get("raw_text") or "")),
                }
            )

        sim_key = str(row.get("sim_slot") or "unknown")
        sim_counts[sim_key] = sim_counts.get(sim_key, 0) + 1

    classes = sorted(
        class_stats.values(),
        key=lambda item: (-int(item["count"]), str(item["class"])),
    )
    sim_breakdown = [
        {"sim_slot": key, "count": value}
        for key, value in sorted(sim_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "status": "ok",
        "generated_at_utc": _utc_now_iso(),
        "limit": limit,
        "sim_slot_filter": sim_slot,
        "scanned_failed_rows": len(rows),
        "receipt_like_count": sum(
            int(item["count"]) for item in classes if bool(item.get("is_receipt"))
        ),
        "unknown_count": sum(
            int(item["count"]) for item in classes if str(item.get("class")) == "unknown_unparsed"
        ),
        "classes": classes,
        "sim_breakdown": sim_breakdown,
    }
