"""Automation utilities: backups and scheduled operational runs."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pesa_logger.monitoring import heartbeat_status
from pesa_logger.reports import export_csv, export_excel, weekly_summary


def backup_database(
    db_path: str = "pesa_logger.db",
    backup_dir: str = "backups",
    keep_last: int = 14,
) -> str:
    """Create a consistent SQLite backup and return the backup file path."""
    if keep_last < 1:
        raise ValueError("keep_last must be >= 1")

    src_path = Path(db_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_root / f"{src_path.stem}_{stamp}.db"

    src_conn = sqlite3.connect(str(src_path))
    dst_conn = sqlite3.connect(str(target))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    backups = sorted(backup_root.glob(f"{src_path.stem}_*.db"))
    stale = backups[:-keep_last]
    for old in stale:
        old.unlink(missing_ok=True)

    return str(target)


def run_scheduled_cycle(
    db_path: str = "pesa_logger.db",
    backup_dir: str = "backups",
    export_dir: str = "exports",
    silence_threshold_hours: float = 24.0,
    now_utc: Optional[datetime] = None,
) -> dict:
    """Run one deterministic automation cycle and return execution results."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    heartbeat = heartbeat_status(
        db_path=db_path,
        threshold_hours=silence_threshold_hours,
        now_utc=now,
        record=True,
    )
    backup_path = backup_database(db_path=db_path, backup_dir=backup_dir)

    exports = {}
    # Sunday in Python's datetime weekday convention.
    if now.weekday() == 6:
        os.makedirs(export_dir, exist_ok=True)
        stamp = now.strftime("%Y%m%d")
        csv_path = os.path.join(export_dir, f"weekly_transactions_{stamp}.csv")
        xlsx_path = os.path.join(export_dir, f"weekly_transactions_{stamp}.xlsx")

        summary = weekly_summary(db_path=db_path, weeks=1)
        export_csv(db_path=db_path, output_path=csv_path)
        export_excel(db_path=db_path, output_path=xlsx_path)
        exports = {
            "weekly_summary": summary,
            "csv_path": csv_path,
            "excel_path": xlsx_path,
        }

    return {
        "ran_at_utc": now.replace(tzinfo=None).isoformat(),
        "heartbeat": heartbeat,
        "backup_path": backup_path,
        "weekly_exports": exports,
    }


def run_scheduler_loop(
    interval_minutes: int = 60,
    db_path: str = "pesa_logger.db",
    backup_dir: str = "backups",
    export_dir: str = "exports",
    silence_threshold_hours: float = 24.0,
) -> None:
    """Run scheduler loop forever at fixed intervals."""
    if interval_minutes < 1:
        raise ValueError("interval_minutes must be >= 1")

    while True:
        run_scheduled_cycle(
            db_path=db_path,
            backup_dir=backup_dir,
            export_dir=export_dir,
            silence_threshold_hours=silence_threshold_hours,
        )
        time.sleep(interval_minutes * 60)
