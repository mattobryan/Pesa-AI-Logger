"""Tests for failed-message classification reporting."""

import pytest

from pesa_logger.database import (
    close_connection,
    init_db,
    save_inbox_sms,
    update_inbox_parse_status,
)
from pesa_logger.failure_report import build_failed_report, classify_failed_message


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "failure_report.db")
    init_db(path)
    yield path
    close_connection(path)


def test_classify_fuliza_drawdown_notice():
    result = classify_failed_message(
        "RDG6CIQWO4 Confirmed. Fuliza M-PESA amount is Ksh 60.00. "
        "Interest charged Ksh 0.60. Total Fuliza M-PESA outstanding amount is Ksh 309.33."
    )
    assert result["class"] == "fuliza_drawdown_notice"
    assert result["is_receipt"] is True


def test_build_failed_report_groups_and_filters_by_sim_slot(db):
    sim1 = save_inbox_sms(
        "RDG6CIQWO4 Confirmed. Fuliza M-PESA amount is Ksh 60.00. Interest charged Ksh 0.60.",
        db_path=db,
        source="android-termux|sim:1|sender:MPESA",
    )
    sim2 = save_inbox_sms(
        "RIC2JWGDRA confirmed.You bought Ksh100.00 of airtime on 12/9/23 at 10:11 AM.",
        db_path=db,
        source="android-termux|sim:2|sender:MPESA",
    )

    update_inbox_parse_status(
        inbox_id=sim1["id"],
        parse_status="failed",
        parse_error="Could not parse SMS as M-Pesa transaction",
        db_path=db,
    )
    update_inbox_parse_status(
        inbox_id=sim2["id"],
        parse_status="failed",
        parse_error="Could not parse SMS as M-Pesa transaction",
        db_path=db,
    )

    all_rows = build_failed_report(db_path=db, limit=100, sample_size=2)
    assert all_rows["scanned_failed_rows"] == 2
    all_classes = {item["class"] for item in all_rows["classes"]}
    assert "fuliza_drawdown_notice" in all_classes
    assert "airtime_purchase_receipt" in all_classes

    sim1_only = build_failed_report(db_path=db, limit=100, sample_size=2, sim_slot="1")
    assert sim1_only["scanned_failed_rows"] == 1
    assert sim1_only["classes"][0]["class"] == "fuliza_drawdown_notice"
