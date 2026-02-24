"""Tests for the SQLite database layer."""

import os
import tempfile

import pytest

from pesa_logger.database import (
    close_connection,
    delete_transaction,
    get_transaction,
    get_inbox_sms,
    init_db,
    list_inbox_sms,
    list_transactions,
    log_report_run,
    save_inbox_sms,
    save_transaction,
    update_category,
    update_inbox_parse_status,
)
from pesa_logger.parser import Transaction


def _make_tx(tid="TEST001", tx_type="send", amount=500.0, balance=4500.0):
    return Transaction(
        transaction_id=tid,
        type=tx_type,
        amount=amount,
        balance=balance,
        raw_sms="test sms",
    )


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    yield path
    close_connection(path)


class TestInitDb:
    def test_creates_file(self, tmp_path):
        path = str(tmp_path / "new.db")
        init_db(path)
        assert os.path.exists(path)
        close_connection(path)


class TestSaveTransaction:
    def test_saves_successfully(self, db):
        tx = _make_tx()
        row_id = save_transaction(tx, db_path=db)
        assert row_id >= 0

    def test_idempotent_duplicate(self, db):
        tx = _make_tx()
        save_transaction(tx, db_path=db)
        save_transaction(tx, db_path=db)  # second save must not raise
        rows = list_transactions(db_path=db)
        assert len(rows) == 1

    def test_saves_multiple(self, db):
        save_transaction(_make_tx("T1"), db_path=db)
        save_transaction(_make_tx("T2"), db_path=db)
        rows = list_transactions(db_path=db)
        assert len(rows) == 2


class TestGetTransaction:
    def test_retrieves_saved(self, db):
        tx = _make_tx("FIND_ME")
        save_transaction(tx, db_path=db)
        result = get_transaction("FIND_ME", db_path=db)
        assert result is not None
        assert result["transaction_id"] == "FIND_ME"
        assert result["amount"] == 500.0

    def test_returns_none_for_missing(self, db):
        assert get_transaction("NOPE", db_path=db) is None


class TestListTransactions:
    def test_filter_by_type(self, db):
        save_transaction(_make_tx("T1", tx_type="send"), db_path=db)
        save_transaction(_make_tx("T2", tx_type="receive"), db_path=db)
        rows = list_transactions(db_path=db, tx_type="send")
        assert all(r["type"] == "send" for r in rows)
        assert len(rows) == 1

    def test_filter_by_category(self, db):
        tx = _make_tx("T3")
        tx.category = "Utilities"
        save_transaction(tx, db_path=db)
        rows = list_transactions(db_path=db, category="Utilities")
        assert len(rows) == 1
        assert rows[0]["category"] == "Utilities"

    def test_filter_by_sim_slot(self, db):
        inbox_sim1 = save_inbox_sms(
            "SIM1 Confirmed. Ksh10 sent.",
            db_path=db,
            source="android-termux|sim:1|sender:MPESA",
        )
        inbox_sim2 = save_inbox_sms(
            "SIM2 Confirmed. Ksh20 sent.",
            db_path=db,
            source="android-termux|sim:2|sender:MPESA",
        )

        save_transaction(
            _make_tx("SIM1TX"),
            db_path=db,
            raw_sms_id=inbox_sim1["id"],
            normalized_hash=inbox_sim1["normalized_hash"],
        )
        save_transaction(
            _make_tx("SIM2TX"),
            db_path=db,
            raw_sms_id=inbox_sim2["id"],
            normalized_hash=inbox_sim2["normalized_hash"],
        )

        rows = list_transactions(db_path=db, sim_slot="2")
        assert len(rows) == 1
        assert rows[0]["transaction_id"] == "SIM2TX"
        assert rows[0]["sim_slot"] == "2"


class TestUpdateCategory:
    def test_updates_category(self, db):
        save_transaction(_make_tx("UPD1"), db_path=db)
        update_category("UPD1", "Education", db_path=db)
        row = get_transaction("UPD1", db_path=db)
        assert row["category"] == "Education"


class TestDeleteTransaction:
    def test_deletes_transaction(self, db):
        save_transaction(_make_tx("DEL1"), db_path=db)
        delete_transaction("DEL1", db_path=db)
        assert get_transaction("DEL1", db_path=db) is None


class TestInboxSms:
    def test_saves_raw_sms(self, db):
        row = save_inbox_sms("ABC Confirmed. Ksh10 sent.", db_path=db, source="test")
        assert row["id"] > 0
        assert row["parse_status"] == "pending"

    def test_dedupes_identical_sms(self, db):
        first = save_inbox_sms("ABC Confirmed. Ksh10 sent.", db_path=db, source="test")
        second = save_inbox_sms("ABC   Confirmed.   Ksh10 sent.", db_path=db, source="test")
        assert first["id"] == second["id"]
        assert second["duplicate"] is True

    def test_updates_parse_status(self, db):
        row = save_inbox_sms("ABC Confirmed. Ksh10 sent.", db_path=db, source="test")
        update_inbox_parse_status(
            inbox_id=row["id"],
            parse_status="failed",
            parse_error="test failure",
            db_path=db,
        )
        updated = get_inbox_sms(inbox_id=row["id"], db_path=db)
        assert updated["parse_status"] == "failed"
        assert updated["parse_error"] == "test failure"

    def test_list_inbox_can_filter_by_sim_slot(self, db):
        save_inbox_sms(
            "AAA Confirmed. Ksh10 sent.",
            db_path=db,
            source="android-termux|sim:1|sender:MPESA",
        )
        save_inbox_sms(
            "BBB Confirmed. Ksh20 sent.",
            db_path=db,
            source="android-termux|sim:2|sender:MPESA",
        )

        rows = list_inbox_sms(db_path=db, sim_slot="1", limit=50)
        assert len(rows) == 1
        assert rows[0]["sim_slot"] == "1"


class TestReportRuns:
    def test_logs_report_run(self, db):
        row_id = log_report_run(
            report_type="weekly_summary",
            db_path=db,
            period_start_utc="2026-02-01T00:00:00",
            period_end_utc="2026-02-07T23:59:59",
            tz="Africa/Nairobi",
            output_path="exports/weekly.csv",
        )
        assert row_id > 0
