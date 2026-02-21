#!/usr/bin/env python3
"""Run one automation cycle (heartbeat + backup + Sunday exports)."""

from __future__ import annotations

import argparse
import json

from pesa_logger.automation import run_scheduled_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one scheduled maintenance cycle")
    parser.add_argument("--db", default="pesa_logger.db", help="Database path")
    parser.add_argument("--backup-dir", default="backups", help="Backup output directory")
    parser.add_argument("--export-dir", default="exports", help="Export output directory")
    parser.add_argument(
        "--silence-hours",
        type=float,
        default=24.0,
        help="No-SMS alert threshold in hours",
    )
    args = parser.parse_args()

    result = run_scheduled_cycle(
        db_path=args.db,
        backup_dir=args.backup_dir,
        export_dir=args.export_dir,
        silence_threshold_hours=args.silence_hours,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
