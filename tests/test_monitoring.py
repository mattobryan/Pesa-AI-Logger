"""Tests for heartbeat/silence monitoring."""

from datetime import datetime, timedelta, timezone

import pytest

from pesa_logger.database import close_connection, list_heartbeat_checks
from pesa_logger.ingestion import ingest_sms_text
from pesa_logger.monitoring import heartbeat_status


SEND_SMS = (
    "HB1001 Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "monitoring_test.db")
    yield path
    close_connection(path)


def test_alert_when_no_messages(db):
    now = datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc)
    result = heartbeat_status(db_path=db, threshold_hours=24, now_utc=now, record=True)
    assert result["status"] == "alert"
    assert result["alert"] is True
    assert result["reason"] == "no_messages_received"

    checks = list_heartbeat_checks(db_path=db, limit=1)
    assert len(checks) == 1
    assert checks[0]["status"] == "alert"


def test_ok_when_recent_message_exists(db):
    ingest_sms_text(SEND_SMS, db_path=db, source="test")
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    result = heartbeat_status(db_path=db, threshold_hours=24, now_utc=now, record=False)
    assert result["status"] == "ok"
    assert result["alert"] is False
    assert result["last_sms_received_utc"] is not None
