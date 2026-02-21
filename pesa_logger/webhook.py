"""Webhook / API ingestion layer.

Exposes a lightweight Flask application that:
* Accepts raw M-Pesa SMS text via HTTP POST
* Parses, categorises, and persists each transaction
* Returns JSON responses

Run with:
    python -m pesa_logger.webhook
or via the main entry point:
    python main.py --serve
"""

from __future__ import annotations

import os
from typing import Optional

from pesa_logger.categorizer import categorize_and_apply, tag_transaction
from pesa_logger.database import init_db, save_transaction
from pesa_logger.parser import parse_sms


def create_app(db_path: Optional[str] = None) -> "Flask":  # type: ignore[name-defined]
    """Create and configure the Flask application."""
    try:
        from flask import Flask, jsonify, request
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Flask is required for the webhook server. "
            "Install it with: pip install flask"
        ) from exc

    app = Flask(__name__)
    _db = db_path or os.environ.get("PESA_DB_PATH", "pesa_logger.db")

    init_db(_db)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "db": _db})

    @app.route("/sms", methods=["POST"])
    def ingest_sms():
        """Accept a raw SMS and process it.

        Expected JSON body::

            {"sms": "<raw M-Pesa SMS text>"}

        Alternatively, the raw SMS text may be sent as plain text.
        """
        if request.is_json:
            body = request.get_json(silent=True) or {}
            sms_text = body.get("sms", "")
        else:
            sms_text = request.get_data(as_text=True)

        if not sms_text:
            return jsonify({"error": "No SMS text provided"}), 400

        tx = parse_sms(sms_text)
        if tx is None:
            return jsonify({"error": "Could not parse SMS as M-Pesa transaction"}), 422

        categorize_and_apply(tx)
        tag_transaction(tx)
        save_transaction(tx, db_path=_db)

        return jsonify({"status": "saved", "transaction": tx.to_dict()}), 201

    @app.route("/transactions", methods=["GET"])
    def list_all():
        """Return all stored transactions as JSON."""
        from pesa_logger.database import list_transactions

        tx_type = request.args.get("type")
        category = request.args.get("category")
        limit = int(request.args.get("limit", 100))

        rows = list_transactions(
            db_path=_db,
            tx_type=tx_type or None,
            category=category or None,
            limit=limit,
        )
        return jsonify(rows)

    @app.route("/analytics/insights", methods=["GET"])
    def insights():
        """Return AI-generated financial insights."""
        from pesa_logger.analytics import generate_insights

        days = int(request.args.get("days", 30))
        result = generate_insights(db_path=_db, days=days)
        return jsonify({"insights": result})

    @app.route("/analytics/summary/weekly", methods=["GET"])
    def weekly():
        """Return weekly financial summary."""
        from pesa_logger.reports import weekly_summary

        weeks = int(request.args.get("weeks", 4))
        return jsonify(weekly_summary(db_path=_db, weeks=weeks))

    @app.route("/analytics/summary/monthly", methods=["GET"])
    def monthly():
        """Return monthly financial summary."""
        from pesa_logger.reports import monthly_summary

        months = int(request.args.get("months", 6))
        return jsonify(monthly_summary(db_path=_db, months=months))

    @app.route("/analytics/anomalies", methods=["GET"])
    def anomalies():
        """Return detected anomalies."""
        from pesa_logger.anomaly import detect_anomalies

        lookback = int(request.args.get("days", 90))
        result = detect_anomalies(db_path=_db, lookback_days=lookback)
        return jsonify([a.to_dict() for a in result])

    @app.route("/export/csv", methods=["GET"])
    def export_csv_route():
        """Stream a CSV export of all transactions."""
        from flask import Response

        from pesa_logger.reports import export_csv

        content = export_csv(db_path=_db)
        return Response(
            content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=transactions.csv"},
        )

    return app


if __name__ == "__main__":  # pragma: no cover
    port = int(os.environ.get("PORT", 5000))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=False)
