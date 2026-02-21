"""Tests for the financial reports and export module."""

import os
import pytest
from datetime import datetime

from pesa_logger.database import close_connection, init_db, save_transaction
from pesa_logger.parser import Transaction
from pesa_logger.reports import export_csv, monthly_summary, weekly_summary


def _tx(tid, tx_type="send", amount=500.0, category="Shopping", ts=None):
    t = Transaction(
        transaction_id=tid,
        type=tx_type,
        amount=amount,
        balance=5000.0,
        category=category,
        raw_sms="test",
    )
    t.timestamp = ts or datetime(2026, 2, 15, 10, 0)
    return t


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "reports_test.db")
    init_db(path)
    # Insert some sample transactions
    save_transaction(_tx("R1", "send", 500, "Shopping"), db_path=path)
    save_transaction(_tx("R2", "receive", 2000, "Income"), db_path=path)
    save_transaction(_tx("R3", "paybill", 1200, "Utilities"), db_path=path)
    yield path
    close_connection(path)


class TestWeeklySummary:
    def test_returns_dict(self, db):
        result = weekly_summary(db_path=db)
        assert isinstance(result, dict)

    def test_summary_has_correct_structure(self, db):
        result = weekly_summary(db_path=db)
        for week, stats in result.items():
            assert "total_in" in stats
            assert "total_out" in stats
            assert "net" in stats
            assert "transaction_count" in stats


class TestMonthlySummary:
    def test_returns_dict(self, db):
        result = monthly_summary(db_path=db)
        assert isinstance(result, dict)

    def test_aggregates_correctly(self, db):
        result = monthly_summary(db_path=db)
        # All our test transactions are in 2026-02
        assert "2026-02" in result
        month = result["2026-02"]
        assert month["total_in"] == 2000.0
        assert month["total_out"] == 1700.0  # 500 + 1200
        assert month["transaction_count"] == 3


class TestExportCsv:
    def test_returns_string(self, db):
        content = export_csv(db_path=db)
        assert isinstance(content, str)

    def test_has_header(self, db):
        content = export_csv(db_path=db)
        assert "transaction_id" in content

    def test_writes_file(self, db, tmp_path):
        output = str(tmp_path / "out.csv")
        export_csv(db_path=db, output_path=output)
        assert os.path.exists(output)
        with open(output) as f:
            lines = f.readlines()
        assert len(lines) >= 4  # header + 3 transactions
