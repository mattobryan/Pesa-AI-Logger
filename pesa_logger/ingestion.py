"""SMS ingestion orchestration.

This module enforces the raw-first contract:
1. Store raw SMS in inbox_sms.
2. Parse and enrich.
3. Persist canonical transaction if valid and non-duplicate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pesa_logger.categorizer import categorize_and_apply, tag_transaction
from pesa_logger.database import (
    get_transaction,
    get_transaction_by_raw_sms_id,
    list_inbox_sms,
    save_inbox_sms,
    save_transaction,
    update_inbox_parse_status,
)
from pesa_logger.parser import PARSER_VERSION, parse_sms


def ingest_sms_text(
    sms_text: str,
    db_path: str = "pesa_logger.db",
    source: str = "webhook",
    fallback_event_time_utc: Optional[str] = None,
) -> dict:
    """Ingest a raw SMS and return a status payload."""
    inbox = save_inbox_sms(
        raw_text=sms_text,
        source=source,
        parser_version=PARSER_VERSION,
        db_path=db_path,
    )
    inbox_id = int(inbox["id"])
    normalized_hash = str(inbox["normalized_hash"])

    if inbox.get("duplicate"):
        existing = get_transaction_by_raw_sms_id(inbox_id, db_path=db_path)
        return {
            "status": "duplicate",
            "message": "Duplicate raw SMS ignored",
            "inbox_id": inbox_id,
            "transaction": existing,
        }

    tx = parse_sms(sms_text)
    if tx is None:
        update_inbox_parse_status(
            inbox_id=inbox_id,
            parse_status="failed",
            parse_error="Could not parse SMS as M-Pesa transaction",
            parser_version=PARSER_VERSION,
            db_path=db_path,
        )
        return {
            "status": "failed",
            "error": "Could not parse SMS as M-Pesa transaction",
            "inbox_id": inbox_id,
        }

    if tx.timestamp is None and fallback_event_time_utc:
        try:
            dt = datetime.fromisoformat(str(fallback_event_time_utc).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            tx.timestamp = dt.astimezone(timezone.utc)
        except ValueError:
            # Keep parser-derived value when fallback metadata is malformed.
            pass

    categorize_and_apply(tx)
    tag_transaction(tx)

    row_id = save_transaction(
        tx=tx,
        db_path=db_path,
        raw_sms_id=inbox_id,
        normalized_hash=normalized_hash,
        parser_version=PARSER_VERSION,
    )

    if row_id == 0:
        update_inbox_parse_status(
            inbox_id=inbox_id,
            parse_status="duplicate",
            parse_error="Duplicate canonical transaction ignored",
            parser_version=PARSER_VERSION,
            db_path=db_path,
        )
        existing: Optional[dict] = None
        if tx.transaction_id:
            existing = get_transaction(tx.transaction_id, db_path=db_path)
        return {
            "status": "duplicate",
            "message": "Duplicate canonical transaction ignored",
            "inbox_id": inbox_id,
            "transaction": existing or tx.to_dict(),
        }

    update_inbox_parse_status(
        inbox_id=inbox_id,
        parse_status="success",
        parse_error=None,
        parser_version=PARSER_VERSION,
        db_path=db_path,
    )
    return {
        "status": "saved",
        "inbox_id": inbox_id,
        "transaction_row_id": row_id,
        "transaction": tx.to_dict(),
    }


def reparse_failed_inbox_sms(
    db_path: str = "pesa_logger.db",
    limit: int = 1000,
) -> dict:
    """Re-run parser over raw inbox rows currently marked as failed."""
    rows = list_inbox_sms(
        db_path=db_path,
        limit=limit,
        oldest_first=True,
        parse_status="failed",
    )
    summary = {
        "status": "ok",
        "scanned": len(rows),
        "reparsed_saved": 0,
        "duplicate": 0,
        "still_failed": 0,
    }

    for row in rows:
        inbox_id = int(row["id"])
        sms_text = str(row.get("raw_text") or "")
        normalized_hash = str(row.get("normalized_hash") or "")

        tx = parse_sms(sms_text)
        if tx is None:
            update_inbox_parse_status(
                inbox_id=inbox_id,
                parse_status="failed",
                parse_error="Could not parse SMS as M-Pesa transaction",
                parser_version=PARSER_VERSION,
                db_path=db_path,
            )
            summary["still_failed"] += 1
            continue

        categorize_and_apply(tx)
        tag_transaction(tx)
        row_id = save_transaction(
            tx=tx,
            db_path=db_path,
            raw_sms_id=inbox_id,
            normalized_hash=normalized_hash,
            parser_version=PARSER_VERSION,
        )
        if row_id == 0:
            update_inbox_parse_status(
                inbox_id=inbox_id,
                parse_status="duplicate",
                parse_error="Duplicate canonical transaction ignored",
                parser_version=PARSER_VERSION,
                db_path=db_path,
            )
            summary["duplicate"] += 1
        else:
            update_inbox_parse_status(
                inbox_id=inbox_id,
                parse_status="success",
                parse_error=None,
                parser_version=PARSER_VERSION,
                db_path=db_path,
            )
            summary["reparsed_saved"] += 1

    return summary
