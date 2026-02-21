#!/usr/bin/env python3
"""Create a local SQLite backup for Pesa AI Logger."""

from __future__ import annotations

import argparse
import json

from pesa_logger.automation import backup_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup SQLite ledger database")
    parser.add_argument("--db", default="pesa_logger.db", help="Path to source DB")
    parser.add_argument("--backup-dir", default="backups", help="Backup output directory")
    parser.add_argument("--keep-last", type=int, default=14, help="Number of backups to retain")
    args = parser.parse_args()

    path = backup_database(
        db_path=args.db,
        backup_dir=args.backup_dir,
        keep_last=args.keep_last,
    )
    print(json.dumps({"status": "ok", "backup_path": path}, indent=2))


if __name__ == "__main__":
    main()
