"""Tests for the SQLite database layer."""

import os
import tempfile

import pytest

from pesa_logger.database import (
    close_connection,
    delete_transaction,
    get_transaction,
    init_db,
    list_transactions,
    save_transaction,
    update_category,
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
