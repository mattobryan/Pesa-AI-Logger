#!/usr/bin/env python3
"""Pesa AI Logger — main entry point.

Usage examples
--------------
Process a single SMS from the command line::

    python main.py --sms "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM. New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."

Start the webhook / API server::

    python main.py --serve [--port 5000] [--db pesa_logger.db]

Export all transactions to CSV::

    python main.py --export-csv [--output transactions.csv]

Show financial insights::

    python main.py --insights [--days 30]

Show anomalies::

    python main.py --anomalies
"""

import argparse
import json
import sys


def _parse_args():
    parser = argparse.ArgumentParser(
        prog="pesa-logger",
        description="MPESA Hybrid AI Logger — parse, store, and analyse M-Pesa SMS",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --sms
    sms_cmd = subparsers.add_parser("sms", help="Parse and store a single SMS")
    sms_cmd.add_argument("text", help="Raw M-Pesa SMS text")
    sms_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --serve
    serve_cmd = subparsers.add_parser("serve", help="Start the webhook API server")
    serve_cmd.add_argument("--port", type=int, default=5000)
    serve_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --export-csv
    csv_cmd = subparsers.add_parser("export-csv", help="Export transactions to CSV")
    csv_cmd.add_argument("--output", default="transactions.csv")
    csv_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --export-excel
    excel_cmd = subparsers.add_parser(
        "export-excel", help="Export transactions to Excel"
    )
    excel_cmd.add_argument("--output", default="transactions.xlsx")
    excel_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --insights
    insights_cmd = subparsers.add_parser(
        "insights", help="Show AI-generated financial insights"
    )
    insights_cmd.add_argument("--days", type=int, default=30)
    insights_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --anomalies
    anomaly_cmd = subparsers.add_parser("anomalies", help="Show detected anomalies")
    anomaly_cmd.add_argument("--days", type=int, default=90)
    anomaly_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --summary
    summary_cmd = subparsers.add_parser(
        "summary", help="Show weekly or monthly financial summary"
    )
    summary_cmd.add_argument(
        "--period", choices=["weekly", "monthly"], default="monthly"
    )
    summary_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --heartbeat
    hb_cmd = subparsers.add_parser("heartbeat", help="Run ingestion heartbeat check")
    hb_cmd.add_argument("--hours", type=float, default=24.0, help="Silence threshold")
    hb_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --backup
    backup_cmd = subparsers.add_parser("backup", help="Create a database backup")
    backup_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    backup_cmd.add_argument("--backup-dir", default="backups", help="Backup directory")
    backup_cmd.add_argument("--keep-last", type=int, default=14, help="Backups to retain")

    # --scheduler-once
    sched_cmd = subparsers.add_parser(
        "scheduler-once",
        help="Run one maintenance cycle (heartbeat, backup, Sunday exports)",
    )
    sched_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    sched_cmd.add_argument("--backup-dir", default="backups", help="Backup directory")
    sched_cmd.add_argument("--export-dir", default="exports", help="Export directory")
    sched_cmd.add_argument("--hours", type=float, default=24.0, help="Silence threshold")

    # --validate-corpus
    corpus_cmd = subparsers.add_parser(
        "validate-corpus",
        help="Validate parser behavior against a JSONL corpus",
    )
    corpus_cmd.add_argument(
        "--path",
        default="corpus/mpesa_sms_corpus.jsonl",
        help="Corpus JSONL path",
    )
    corpus_cmd.add_argument(
        "--min-success",
        type=float,
        default=0.98,
        help="Minimum parser success rate gate",
    )

    # --correct
    correct_cmd = subparsers.add_parser("correct", help="Apply audited transaction correction")
    correct_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    correct_cmd.add_argument("--transaction-id", required=True, help="Transaction ID")
    correct_cmd.add_argument(
        "--set",
        action="append",
        required=True,
        help="Field update in key=value format (repeatable)",
    )
    correct_cmd.add_argument("--reason", required=True, help="Reason for correction")
    correct_cmd.add_argument("--by", default="cli", help="Operator identifier")

    # --list-corrections
    list_corr_cmd = subparsers.add_parser(
        "list-corrections", help="List transaction correction audit records"
    )
    list_corr_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    list_corr_cmd.add_argument("--transaction-id", default=None, help="Optional transaction filter")
    list_corr_cmd.add_argument("--limit", type=int, default=100, help="Rows to return")

    # --list-inbox
    list_inbox_cmd = subparsers.add_parser("list-inbox", help="List raw inbox SMS rows")
    list_inbox_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    list_inbox_cmd.add_argument("--limit", type=int, default=200, help="Rows to return")
    list_inbox_cmd.add_argument(
        "--oldest-first",
        action="store_true",
        help="Return oldest rows first",
    )

    # --verify-ledger
    verify_ledger_cmd = subparsers.add_parser(
        "verify-ledger",
        help="Verify tamper-evident ledger chain integrity",
    )
    verify_ledger_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")

    # --ledger-events
    ledger_events_cmd = subparsers.add_parser(
        "ledger-events",
        help="List recent tamper-evident ledger chain events",
    )
    ledger_events_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    ledger_events_cmd.add_argument("--limit", type=int, default=200, help="Rows to return")
    ledger_events_cmd.add_argument(
        "--entity-table",
        default=None,
        help="Optional table filter (e.g. inbox_sms, transactions)",
    )

    # --rebuild-ledger
    rebuild_ledger_cmd = subparsers.add_parser(
        "rebuild-ledger",
        help="Backfill/rebuild tamper-evident ledger chain from existing DB rows",
    )
    rebuild_ledger_cmd.add_argument("--db", default="pesa_logger.db", help="Database path")
    rebuild_ledger_cmd.add_argument(
        "--force",
        action="store_true",
        help="Rebuild from scratch even when ledger_chain already has events",
    )

    return parser.parse_args()


def main():
    args = _parse_args()

    if args.command == "sms":
        from pesa_logger.ingestion import ingest_sms_text

        result = ingest_sms_text(
            sms_text=args.text,
            db_path=args.db,
            source="cli",
        )
        if result["status"] == "failed":
            print(json.dumps(result, indent=2))
            sys.exit(1)
        print(json.dumps(result, indent=2))

    elif args.command == "serve":
        import os
        from pesa_logger.webhook import create_app

        os.environ["PESA_DB_PATH"] = args.db
        app = create_app(db_path=args.db)
        print(f"Starting Pesa AI Logger server on port {args.port} …")
        app.run(host="0.0.0.0", port=args.port, debug=False)

    elif args.command == "export-csv":
        from pesa_logger.reports import export_csv

        export_csv(db_path=args.db, output_path=args.output)
        print(f"Exported to {args.output}")

    elif args.command == "export-excel":
        from pesa_logger.reports import export_excel

        export_excel(db_path=args.db, output_path=args.output)
        print(f"Exported to {args.output}")

    elif args.command == "insights":
        from pesa_logger.analytics import generate_insights

        insights = generate_insights(db_path=args.db, days=args.days)
        for insight in insights:
            print(f"• {insight}")

    elif args.command == "anomalies":
        from pesa_logger.anomaly import detect_anomalies

        anomalies = detect_anomalies(db_path=args.db, lookback_days=args.days)
        if not anomalies:
            print("No anomalies detected.")
        for a in anomalies:
            print(json.dumps(a.to_dict(), indent=2))

    elif args.command == "summary":
        from pesa_logger.reports import monthly_summary, weekly_summary

        if args.period == "weekly":
            data = weekly_summary(db_path=args.db)
        else:
            data = monthly_summary(db_path=args.db)
        print(json.dumps(data, indent=2))

    elif args.command == "heartbeat":
        from pesa_logger.monitoring import heartbeat_status

        result = heartbeat_status(
            db_path=args.db,
            threshold_hours=args.hours,
            record=True,
        )
        print(json.dumps(result, indent=2))
        if result["alert"]:
            sys.exit(2)

    elif args.command == "backup":
        from pesa_logger.automation import backup_database

        output = backup_database(
            db_path=args.db,
            backup_dir=args.backup_dir,
            keep_last=args.keep_last,
        )
        print(json.dumps({"backup_path": output}, indent=2))

    elif args.command == "scheduler-once":
        from pesa_logger.automation import run_scheduled_cycle

        result = run_scheduled_cycle(
            db_path=args.db,
            backup_dir=args.backup_dir,
            export_dir=args.export_dir,
            silence_threshold_hours=args.hours,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "validate-corpus":
        from pesa_logger.corpus import validate_corpus

        result = validate_corpus(
            path=args.path,
            min_success_rate=args.min_success,
        )
        print(json.dumps(result, indent=2))
        if not result["passed_gate"]:
            sys.exit(1)

    elif args.command == "correct":
        from pesa_logger.database import apply_transaction_correction

        updates = {}
        for item in args.set:
            if "=" not in item:
                print(f"Invalid --set value (expected key=value): {item}")
                sys.exit(1)
            key, value = item.split("=", 1)
            updates[key.strip()] = value.strip()

        result = apply_transaction_correction(
            transaction_id=args.transaction_id,
            updates=updates,
            reason=args.reason,
            corrected_by=args.by,
            db_path=args.db,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "list-corrections":
        from pesa_logger.database import list_transaction_corrections

        rows = list_transaction_corrections(
            db_path=args.db,
            transaction_id=args.transaction_id,
            limit=args.limit,
        )
        print(json.dumps(rows, indent=2))

    elif args.command == "list-inbox":
        from pesa_logger.database import list_inbox_sms

        rows = list_inbox_sms(
            db_path=args.db,
            limit=args.limit,
            oldest_first=args.oldest_first,
        )
        print(json.dumps(rows, indent=2))

    elif args.command == "verify-ledger":
        from pesa_logger.database import verify_ledger_chain

        result = verify_ledger_chain(db_path=args.db)
        print(json.dumps(result, indent=2))
        if not result.get("valid"):
            sys.exit(2)

    elif args.command == "ledger-events":
        from pesa_logger.database import list_ledger_events

        rows = list_ledger_events(
            db_path=args.db,
            limit=args.limit,
            entity_table=args.entity_table,
        )
        print(json.dumps(rows, indent=2))

    elif args.command == "rebuild-ledger":
        from pesa_logger.database import rebuild_ledger_chain

        result = rebuild_ledger_chain(
            db_path=args.db,
            force=args.force,
        )
        print(json.dumps(result, indent=2))
        if result.get("status") == "skipped":
            sys.exit(1)
        verification = result.get("verification") or {}
        if verification and not verification.get("valid", False):
            sys.exit(2)

    else:
        print(
            "Pesa AI Logger. Run with --help for usage.\n\n"
            "Commands: sms, serve, export-csv, export-excel, insights, anomalies, summary, "
            "heartbeat, backup, scheduler-once, validate-corpus, correct, list-corrections, "
            "list-inbox, verify-ledger, ledger-events, rebuild-ledger"
        )


if __name__ == "__main__":
    main()
