"""Tests for tamper-evident ledger chain behavior."""

import sqlite3

import pytest

from pesa_logger.database import (
    apply_transaction_correction,
    close_connection,
    init_db,
    list_ledger_events,
    verify_ledger_chain,
)
from pesa_logger.ingestion import ingest_sms_text


SEND_SMS = (
    "LED001 Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "ledger_test.db")
    init_db(path)
    yield path
    close_connection(path)


def test_ingestion_appends_chain_events_and_verifies(db):
    result = ingest_sms_text(SEND_SMS, db_path=db, source="test")
    assert result["status"] == "saved"

    verification = verify_ledger_chain(db_path=db)
    assert verification["valid"] is True
    assert verification["event_count"] >= 2

    events = list_ledger_events(db_path=db, limit=10)
    event_types = {row["event_type"] for row in events}
    assert "inbox_sms_saved" in event_types
    assert "transaction_saved" in event_types


def test_chain_is_append_only(db):
    ingest_sms_text(SEND_SMS, db_path=db, source="test")
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE ledger_chain SET event_type = 'tampered' WHERE chain_index = 1")
        conn.commit()
    conn.close()


def test_correction_appends_chain_event(db):
    ingest_sms_text(SEND_SMS, db_path=db, source="test")
    before = verify_ledger_chain(db_path=db)["event_count"]

    result = apply_transaction_correction(
        transaction_id="LED001",
        updates={"category": "Food"},
        reason="manual category",
        corrected_by="tester",
        db_path=db,
    )
    assert result["status"] == "updated"

    after = verify_ledger_chain(db_path=db)["event_count"]
    assert after > before

    events = list_ledger_events(db_path=db, limit=5)
    assert any(row["event_type"] == "transaction_corrected" for row in events)
