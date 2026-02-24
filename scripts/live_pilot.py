#!/usr/bin/env python3
"""Run a local end-to-end pilot: HTTP ingest -> DB -> ledger verification."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pesa_logger.database import verify_ledger_chain
from pesa_logger.webhook import create_app


SEND_SMS = (
    "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)

RECEIVE_SMS = (
    "BC47YUK Confirmed.You have received Ksh250.00 from JANE DOE 0712345678 on 21/2/26 at"
    " 10:31 AM  New M-PESA balance is Ksh5,250.00."
)


class _ServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int):
        super().__init__(daemon=True)
        from werkzeug.serving import make_server

        self._server = make_server(host, port, app)
        self._ctx = app.app_context()
        self._ctx.push()

    def run(self) -> None:
        self._server.serve_forever()

    def stop(self) -> None:
        self._server.shutdown()
        self._ctx.pop()


def _post(url: str, payload: dict, api_key: str) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return int(resp.getcode()), data


def _counts(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    out = {}
    cur.execute("SELECT COUNT(*) FROM inbox_sms")
    out["inbox_total"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transactions")
    out["transactions_total"] = cur.fetchone()[0]
    cur.execute(
        "SELECT parse_status, COUNT(*) FROM inbox_sms GROUP BY parse_status ORDER BY parse_status"
    )
    out["inbox_by_status"] = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local live pilot")
    parser.add_argument("--host", default="127.0.0.1", help="Server bind host")
    parser.add_argument("--port", type=int, default=5060, help="Server port")
    parser.add_argument(
        "--db",
        default=None,
        help="Optional DB path (defaults to temp file for clean pilot)",
    )
    parser.add_argument("--api-key", default="pilot-secret", help="Pilot API key")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        fd, temp_path = tempfile.mkstemp(prefix="pesa_live_pilot_", suffix=".db")
        os.close(fd)
        db_path = temp_path

    app = create_app(db_path=db_path, api_key=args.api_key)
    server = _ServerThread(app, args.host, args.port)
    server.start()
    time.sleep(0.4)

    try:
        url = f"http://{args.host}:{args.port}/sms"
        posts = []
        for sms, sim_slot in ((SEND_SMS, "1"), (RECEIVE_SMS, "2")):
            code, payload = _post(
                url,
                {
                    "sms": sms,
                    "source": "android-termux",
                    "meta": {"sim_slot": sim_slot, "sender": "MPESA"},
                },
                api_key=args.api_key,
            )
            posts.append({"status_code": code, "status": payload.get("status")})

        result = {
            "status": "ok",
            "db_path": db_path,
            "posts": posts,
            "counts": _counts(db_path),
            "ledger": verify_ledger_chain(db_path=db_path),
        }
        print(json.dumps(result, indent=2))
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
