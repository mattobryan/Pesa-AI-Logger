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

    return parser.parse_args()


def main():
    args = _parse_args()

    if args.command == "sms":
        from pesa_logger.categorizer import categorize_and_apply, tag_transaction
        from pesa_logger.database import save_transaction
        from pesa_logger.parser import parse_sms

        tx = parse_sms(args.text)
        if tx is None:
            print("ERROR: Could not parse the provided text as an M-Pesa SMS.")
            sys.exit(1)
        categorize_and_apply(tx)
        tag_transaction(tx)
        save_transaction(tx, db_path=args.db)
        print(json.dumps(tx.to_dict(), indent=2))

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

    else:
        print(
            "Pesa AI Logger. Run with --help for usage.\n\n"
            "Commands: sms, serve, export-csv, export-excel, insights, anomalies, summary"
        )


if __name__ == "__main__":
    main()
