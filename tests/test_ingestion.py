"""Tests for raw-first SMS ingestion orchestration."""

import pytest

from pesa_logger.database import close_connection, get_inbox_sms, init_db, list_transactions
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
