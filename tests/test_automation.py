"""Tests for automation: backup and scheduler cycle."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pesa_logger.automation import backup_database, run_scheduled_cycle
from pesa_logger.database import close_connection, init_db
from pesa_logger.ingestion import ingest_sms_text


SEND_SMS = (
    "AUTO001 Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "automation_test.db")
    init_db(path)
    ingest_sms_text(SEND_SMS, db_path=path, source="test")
    yield path
    close_connection(path)


def test_backup_database_creates_file(db, tmp_path):
    backup_dir = tmp_path / "backups"
    output = backup_database(db_path=db, backup_dir=str(backup_dir), keep_last=3)
    assert Path(output).exists()
    assert output.endswith(".db")


def test_run_scheduled_cycle_non_sunday(db, tmp_path):
    result = run_scheduled_cycle(
        db_path=db,
        backup_dir=str(tmp_path / "backups"),
        export_dir=str(tmp_path / "exports"),
        silence_threshold_hours=24,
        now_utc=datetime(2026, 2, 23, 9, 0, tzinfo=timezone.utc),  # Monday
    )
    assert result["backup_path"]
    assert result["weekly_exports"] == {}
    assert result["heartbeat"]["status"] in {"ok", "alert"}


def test_run_scheduled_cycle_sunday_generates_exports(db, tmp_path):
    export_dir = tmp_path / "exports"
    result = run_scheduled_cycle(
        db_path=db,
        backup_dir=str(tmp_path / "backups"),
        export_dir=str(export_dir),
        silence_threshold_hours=24,
        now_utc=datetime(2026, 2, 22, 9, 0, tzinfo=timezone.utc),  # Sunday
    )
    weekly = result["weekly_exports"]
    assert "csv_path" in weekly
    assert "excel_path" in weekly
    assert Path(weekly["csv_path"]).exists()
    assert Path(weekly["excel_path"]).exists()
