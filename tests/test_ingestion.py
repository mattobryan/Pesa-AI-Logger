"""Tests for raw-first SMS ingestion orchestration."""

import pytest

from pesa_logger.database import close_connection, get_inbox_sms, get_transaction, init_db, list_transactions
from pesa_logger.ingestion import ingest_sms_text


SEND_SMS = (
    "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "ingestion_test.db")
    init_db(path)
    yield path
    close_connection(path)


def test_saved_path_updates_inbox_to_success(db):
    result = ingest_sms_text(SEND_SMS, db_path=db, source="test")
    assert result["status"] == "saved"

    inbox = get_inbox_sms(inbox_id=result["inbox_id"], db_path=db)
    assert inbox["parse_status"] == "success"


def test_duplicate_sms_does_not_duplicate_transactions(db):
    first = ingest_sms_text(SEND_SMS, db_path=db, source="test")
    second = ingest_sms_text(SEND_SMS, db_path=db, source="test")
    assert first["status"] == "saved"
    assert second["status"] == "duplicate"

    rows = list_transactions(db_path=db)
    assert len(rows) == 1


def test_invalid_sms_is_stored_and_marked_failed(db):
    result = ingest_sms_text("not an mpesa sms", db_path=db, source="test")
    assert result["status"] == "failed"

    inbox = get_inbox_sms(inbox_id=result["inbox_id"], db_path=db)
    assert inbox["parse_status"] == "failed"
    assert "Could not parse" in (inbox["parse_error"] or "")


def test_fallback_event_time_is_used_when_parser_timestamp_missing(db):
    sms_without_inline_time = (
        "TS001 Confirmed. Ksh100.00 sent to JOHN DOE 0712345678."
        " New M-PESA balance is Ksh900.00. Transaction cost, Ksh0.00."
    )
    result = ingest_sms_text(
        sms_without_inline_time,
        db_path=db,
        source="test",
        fallback_event_time_utc="2026-02-20T10:15:00Z",
    )
    assert result["status"] == "saved"

    tx = get_transaction("TS001", db_path=db)
    assert tx["timestamp"] == "2026-02-20T10:15:00"
