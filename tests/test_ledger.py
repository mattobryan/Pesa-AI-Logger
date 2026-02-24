"""Tests for tamper-evident ledger chain behavior."""

import sqlite3

import pytest

from pesa_logger.database import (
    apply_transaction_correction,
    close_connection,
    init_db,
    list_ledger_events,
    rebuild_ledger_chain,
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


def test_rebuild_ledger_backfills_existing_rows(db):
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO inbox_sms
        (received_at_utc, source, raw_text, normalized_hash, parse_status, parse_error, parser_version, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-02-20T10:00:00",
            "android-termux",
            "RB001 Confirmed. Ksh100.00 sent to JOHN DOE 0712345678 on 20/2/26 at 1:00 PM. New M-PESA balance is Ksh900.00. Transaction cost, Ksh0.00.",
            "hash-rb001",
            "success",
            None,
            "v1.0.0",
            "2026-02-20T10:00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO transactions
        (transaction_id, event_time_utc, type, amount, currency, raw_sms_id, normalized_hash, parser_version, raw_sms, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "RB001",
            "2026-02-20T10:00:00",
            "send",
            100.0,
            "KES",
            1,
            "hash-rb001",
            "v1.0.0",
            "RB001 Confirmed...",
            "2026-02-20T10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    pre = verify_ledger_chain(db_path=db)
    assert pre["valid"] is True
    assert pre["event_count"] == 0
    assert pre["note"] == "ledger_chain_empty_with_existing_data"

    rebuilt = rebuild_ledger_chain(db_path=db)
    assert rebuilt["status"] == "rebuilt"
    assert rebuilt["appended"]["inbox_sms_saved"] == 1
    assert rebuilt["appended"]["transaction_saved"] == 1
    assert rebuilt["verification"]["valid"] is True
    assert rebuilt["verification"]["event_count"] == 2
