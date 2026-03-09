"""Webhook / API ingestion layer."""
from __future__ import annotations

import hmac
import os
import secrets
from typing import Optional

from pesa_logger.database import (
    apply_transaction_correction,
    init_db,
    list_heartbeat_checks,
    list_inbox_sms,
    list_ledger_events,
    list_transaction_corrections,
    verify_ledger_chain,
)
from pesa_logger.ingestion import ingest_sms_text
from pesa_logger.monitoring import heartbeat_status
from pesa_logger.failure_report import build_failed_report
from pesa_logger.dashboard import (
    build_dashboard_response,
    build_auth_response,
    build_logout_response,
)

# Maximum size of an incoming request body (2 KB is generous for any SMS)
_MAX_SMS_BYTES = 2 * 1024
# Maximum length of the SMS text string itself
_MAX_SMS_TEXT_LEN = 1200


def create_app(
    db_path: Optional[str] = None,
    api_key: Optional[str] = None,
) -> "Flask":
    """Create and configure the Flask application."""
    try:
        from flask import Flask, jsonify, request, session
    except ImportError as exc:
        raise ImportError(
            "Flask is required. Install it with: pip install flask"
        ) from exc

    app = Flask(__name__)

    # Reject any request body larger than 2 KB — protects the SMS parser
    app.config["MAX_CONTENT_LENGTH"] = _MAX_SMS_BYTES

    session_secret = os.environ.get("SESSION_SECRET")
    if not session_secret:
        session_secret = secrets.token_urlsafe(48)
    app.secret_key = session_secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
    )

    _db = db_path or os.environ.get("PESA_DB_PATH", "pesa_logger.db")
    _api_key = (
        (api_key if api_key is not None else os.environ.get("PESA_API_KEY", "")) or ""
    ).strip()

    init_db(_db)

    # -------------------------------------------------------------------------
    # Error handlers
    # -------------------------------------------------------------------------

    @app.errorhandler(413)
    def request_too_large(e):
        return jsonify({"error": "Request body too large. Maximum SMS payload is 2 KB."}), 413

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _compose_source(base_source: str, meta: Optional[dict]) -> str:
        if not isinstance(meta, dict):
            return base_source
        parts = [base_source.strip() or "webhook"]
        sender = str(meta.get("sender") or "").strip()
        sim_slot = str(meta.get("sim_slot") or meta.get("subscription_id") or "").strip()
        if sim_slot:
            parts.append(f"sim:{sim_slot}")
        if sender:
            parts.append(f"sender:{sender}")
        return "|".join(parts)

    def _has_valid_header_api_key() -> bool:
        if not _api_key:
            return True
        provided = request.headers.get("X-API-Key", "")
        return bool(provided) and hmac.compare_digest(provided, _api_key)

    def _is_request_authorized() -> bool:
        if not _api_key:
            return True
        if _has_valid_header_api_key():
            return True
        return bool(session.get("authenticated"))

    def _require_auth():
        if _is_request_authorized():
            return None
        return jsonify({"error": "Unauthorized"}), 401

    _public_paths = {"/health", "/dashboard", "/auth", "/logout"}

    _route_descriptions = {
        "/health": "Public health status",
        "/health/details": "Detailed health diagnostics",
        "/routes": "Live route inventory",
        "/dashboard": "Web dashboard",
        "/auth": "Dashboard login",
        "/logout": "Dashboard logout",
        "/sms": "Ingest SMS payload",
        "/transactions": "List transactions",
        "/inbox": "List raw inbox messages",
        "/inbox/failed/report": "Classified failed-message report",
        "/analytics/insights": "Generate financial insights",
        "/analytics/summary/weekly": "Weekly summary",
        "/analytics/summary/monthly": "Monthly summary",
        "/analytics/anomalies": "Anomaly detection",
        "/monitor/heartbeat": "Current heartbeat status",
        "/monitor/heartbeat/history": "Heartbeat history",
        "/export/csv": "CSV export",
        "/corrections": "Correction audit + mutation",
        "/ledger/verify": "Ledger-chain verification",
        "/ledger/events": "Ledger event listing",
        "/analytics/full": "Complete analytics report for dashboard",
        "/analytics/health": "Financial health score",
        "/analytics/forecast": "30-day spending forecast",
        "/analytics/counterparties": "Counterparty profiles and risk flags",
    }

    # -------------------------------------------------------------------------
    # Dashboard
    # -------------------------------------------------------------------------

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        error = request.args.get("error") == "1"
        return build_dashboard_response(api_key=_api_key, session=session, error=error)

    @app.route("/auth", methods=["POST"])
    def auth():
        body, code = build_auth_response(request, _api_key, session)
        return jsonify(body), code

    @app.route("/logout", methods=["GET"])
    def logout():
        body, code = build_logout_response(session)
        return jsonify(body), code

    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/health/details", methods=["GET"])
    def health_details():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        return jsonify({"status": "ok", "db": _db, "api_key_required": bool(_api_key)})

    @app.route("/routes", methods=["GET"])
    def routes_inventory():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        rows = []
        for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
            if rule.endpoint == "static":
                continue
            methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
            rows.append({
                "path": rule.rule,
                "methods": methods,
                "endpoint": rule.endpoint,
                "requires_auth": rule.rule not in _public_paths,
                "description": _route_descriptions.get(rule.rule, ""),
            })
        return jsonify(rows)

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    @app.route("/monitor/heartbeat", methods=["GET"])
    def heartbeat():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        threshold = float(request.args.get("threshold_hours", 24))
        record = request.args.get("record", "1").lower() not in {"0", "false", "no"}
        result = heartbeat_status(db_path=_db, threshold_hours=threshold, record=record)
        code = 200 if result["status"] == "ok" else 503
        return jsonify(result), code

    @app.route("/monitor/heartbeat/history", methods=["GET"])
    def heartbeat_history():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        limit = int(request.args.get("limit", 100))
        rows = list_heartbeat_checks(db_path=_db, limit=limit)
        return jsonify(rows)

    # -------------------------------------------------------------------------
    # SMS ingestion
    # -------------------------------------------------------------------------

    @app.route("/sms", methods=["POST"])
    def ingest_sms():
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        if request.is_json:
            body = request.get_json(silent=True) or {}
            sms_text = str(body.get("sms") or "").strip()
            source = body.get("source") or request.headers.get("X-SMS-Source", "webhook")
            source = _compose_source(source, body.get("meta"))
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            fallback_event_time_utc = meta.get("sms_timestamp_utc")
        else:
            sms_text = (request.get_data(as_text=True) or "").strip()
            source = request.headers.get("X-SMS-Source", "webhook")
            fallback_event_time_utc = None

        if not sms_text:
            return jsonify({"error": "No SMS text provided"}), 400

        if len(sms_text) > _MAX_SMS_TEXT_LEN:
            return jsonify({
                "error": f"SMS text too long ({len(sms_text)} chars). Maximum is {_MAX_SMS_TEXT_LEN}."
            }), 422

        result = ingest_sms_text(
            sms_text=sms_text,
            db_path=_db,
            source=source,
            fallback_event_time_utc=fallback_event_time_utc,
        )

        if result["status"] == "saved":
            return jsonify(result), 201
        if result["status"] == "duplicate":
            return jsonify(result), 200
        return jsonify(result), 422

    # -------------------------------------------------------------------------
    # Inbox
    # -------------------------------------------------------------------------

    @app.route("/inbox", methods=["GET"])
    def list_inbox():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        limit = int(request.args.get("limit", 200))
        oldest_first = request.args.get("oldest_first", "0").lower() in {"1", "true", "yes"}
        parse_status = request.args.get("parse_status")
        sim_slot = request.args.get("sim_slot")
        rows = list_inbox_sms(
            db_path=_db,
            limit=limit,
            oldest_first=oldest_first,
            parse_status=parse_status or None,
            sim_slot=sim_slot or None,
        )
        return jsonify(rows)

    @app.route("/inbox/failed/report", methods=["GET"])
    def failed_inbox_report():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        limit = int(request.args.get("limit", 5000))
        sample_size = int(request.args.get("sample_size", 3))
        sim_slot = request.args.get("sim_slot")
        result = build_failed_report(
            db_path=_db, limit=limit, sample_size=sample_size, sim_slot=sim_slot or None
        )
        return jsonify(result)

    # -------------------------------------------------------------------------
    # Transactions
    # -------------------------------------------------------------------------

    @app.route("/transactions", methods=["GET"])
    def list_all():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from pesa_logger.database import list_transactions
        tx_type = request.args.get("type")
        category = request.args.get("category")
        sim_slot = request.args.get("sim_slot")
        limit = int(request.args.get("limit", 100))
        rows = list_transactions(
            db_path=_db,
            tx_type=tx_type or None,
            category=category or None,
            sim_slot=sim_slot or None,
            limit=limit,
        )
        return jsonify(rows)

    # -------------------------------------------------------------------------
    # Analytics
    # -------------------------------------------------------------------------

    @app.route("/analytics/insights", methods=["GET"])
    def insights():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from pesa_logger.analytics import generate_insights
        days = int(request.args.get("days", 30))
        return jsonify({"insights": generate_insights(db_path=_db, days=days)})

    @app.route("/analytics/summary/weekly", methods=["GET"])
    def weekly():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from pesa_logger.reports import weekly_summary
        weeks = int(request.args.get("weeks", 4))
        return jsonify(weekly_summary(db_path=_db, weeks=weeks))

    @app.route("/analytics/summary/monthly", methods=["GET"])
    def monthly():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from pesa_logger.reports import monthly_summary
        months = int(request.args.get("months", 6))
        return jsonify(monthly_summary(db_path=_db, months=months))

    @app.route("/analytics/anomalies", methods=["GET"])
    def anomalies():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from pesa_logger.anomaly import detect_anomalies
        lookback = int(request.args.get("days", 90))
        return jsonify([a.to_dict() for a in detect_anomalies(db_path=_db, lookback_days=lookback)])

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    @app.route("/export/csv", methods=["GET"])
    def export_csv_route():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        from flask import Response
        from pesa_logger.reports import export_csv
        content = export_csv(db_path=_db)
        return Response(
            content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=transactions.csv"},
        )

    # -------------------------------------------------------------------------
    # Corrections
    # -------------------------------------------------------------------------

    @app.route("/corrections", methods=["GET"])
    def list_corrections():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        tx_id = request.args.get("transaction_id")
        limit = int(request.args.get("limit", 200))
        rows = list_transaction_corrections(db_path=_db, transaction_id=tx_id or None, limit=limit)
        return jsonify(rows)

    @app.route("/corrections", methods=["POST"])
    def apply_correction():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        body = request.get_json(silent=True) or {}
        transaction_id = body.get("transaction_id")
        updates = body.get("updates") or {}
        reason = body.get("reason", "")
        corrected_by = body.get("corrected_by", "api")
        if not transaction_id:
            return jsonify({"error": "transaction_id is required"}), 400
        if not isinstance(updates, dict) or not updates:
            return jsonify({"error": "updates must be a non-empty object"}), 400
        if not reason:
            return jsonify({"error": "reason is required"}), 400
        try:
            result = apply_transaction_correction(
                transaction_id=transaction_id,
                updates=updates,
                reason=reason,
                corrected_by=corrected_by,
                db_path=_db,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 200

    # -------------------------------------------------------------------------
    # Ledger
    # -------------------------------------------------------------------------

    @app.route("/ledger/verify", methods=["GET"])
    def verify_ledger():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        result = verify_ledger_chain(db_path=_db)
        return jsonify(result), (200 if result.get("valid") else 409)

    @app.route("/ledger/events", methods=["GET"])
    def ledger_events():
        auth_error = _require_auth()
        if auth_error:
            return auth_error
        limit = int(request.args.get("limit", 200))
        entity_table = request.args.get("entity_table")
        rows = list_ledger_events(db_path=_db, limit=limit, entity_table=entity_table or None)
        return jsonify(rows)
    # -------------------------------------------------------------------------
    # Analytics — full report endpoint
    # -------------------------------------------------------------------------

    @app.route("/analytics/full", methods=["GET"])
    def analytics_full():
        """Return a complete analytics report — powers the analytics dashboard.

        Query params:
            days          : lookback period in days (default 30)
            include_forecast    : 1/0 (default 1)
            include_health      : 1/0 (default 1)
        """
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.analytics import generate_full_report, report_to_dict
        from dataclasses import asdict

        days = max(1, min(365, int(request.args.get("days", 30))))
        include_forecast = request.args.get("include_forecast", "1").lower() not in {"0", "false"}
        include_health = request.args.get("include_health", "1").lower() not in {"0", "false"}

        try:
            report = generate_full_report(
                db_path=_db,
                days=days,
                include_forecast=include_forecast,
                include_health_score=include_health,
            )
            return jsonify(report_to_dict(report)), 200

        except Exception as exc:
            return jsonify({
                "error": "Failed to generate analytics report",
                "detail": str(exc),
            }), 500

    @app.route("/analytics/health", methods=["GET"])
    def analytics_health_score():
        """Return financial health score only — lightweight endpoint."""
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.analytics import financial_health_score
        from dataclasses import asdict

        days = max(1, min(365, int(request.args.get("days", 30))))
        try:
            score = financial_health_score(db_path=_db, days=days)
            return jsonify(asdict(score)), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/analytics/forecast", methods=["GET"])
    def analytics_forecast():
        """Return spending forecast only."""
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.analytics import spending_forecast
        from dataclasses import asdict

        try:
            forecast = spending_forecast(db_path=_db)
            return jsonify(asdict(forecast)), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/analytics/counterparties", methods=["GET"])
    def analytics_counterparties():
        """Return counterparty profiles."""
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.analytics import frequent_counterparties
        from dataclasses import asdict

        days = int(request.args.get("days", 90))
        limit = int(request.args.get("limit", 10))

        try:
            profiles = frequent_counterparties(db_path=_db, days=days, limit=limit)
            return jsonify([asdict(p) for p in profiles]), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    
    # -------------------------------------------------------------------------
    # Ledger — Web3 anchor endpoints (T3)
    # -------------------------------------------------------------------------

    @app.route("/ledger/anchor", methods=["POST"])
    def ledger_anchor():
        """Trigger an on-chain anchor of pending ledger transactions.

        Body (optional JSON):
            { "force": true }   — anchor even if below threshold

        Returns the anchor result including merkle_root and status.
        """
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.web3_anchor import anchor_pending_transactions, Web3Config

        body = request.get_json(silent=True) or {}
        force = bool(body.get("force", False))

        try:
            config = Web3Config()
            result = anchor_pending_transactions(
                db_path=_db,
                config=config,
                force=force,
            )
            status_code = 200 if result.get("anchored") else 202
            return jsonify(result), status_code

        except Exception as exc:
            return jsonify({"error": f"Anchor failed: {exc}"}), 500

    @app.route("/ledger/anchors", methods=["GET"])
    def ledger_anchors():
        """List all on-chain anchor records.

        Query params:
            limit  : max records to return (default 50)
            status : filter by status (confirmed | web3_disabled | failed | pending)
        """
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.web3_anchor import list_anchor_records, get_anchor_summary

        limit = max(1, min(200, int(request.args.get("limit", 50))))
        status_filter = request.args.get("status") or None

        try:
            records = list_anchor_records(
                db_path=_db,
                limit=limit,
                status=status_filter,
            )
            summary = get_anchor_summary(db_path=_db)
            return jsonify({"summary": summary, "anchors": records}), 200

        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/ledger/verify-onchain", methods=["GET"])
    def ledger_verify_onchain():
        """Verify a Merkle root against the Polygon PesaAnchor contract.

        Query params:
            root : Merkle root hex string to verify (required)
                   If omitted, verifies the most recently confirmed anchor.
        """
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.web3_anchor import (
            verify_onchain, list_anchor_records, Web3Config
        )

        merkle_root = request.args.get("root") or ""

        # If no root given, verify the most recent confirmed anchor
        if not merkle_root:
            recent = list_anchor_records(_db, limit=1, status="confirmed")
            if not recent:
                return jsonify({
                    "verified": False,
                    "message": "No confirmed on-chain anchors found. Run POST /ledger/anchor first.",
                }), 404
            merkle_root = recent[0]["merkle_root"]

        try:
            config = Web3Config()
            result = verify_onchain(merkle_root=merkle_root, config=config)
            return jsonify(result), 200

        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/ledger/anchor-summary", methods=["GET"])
    def ledger_anchor_summary():
        """Return Web3 anchor status summary for the dashboard."""
        auth_error = _require_auth()
        if auth_error:
            return auth_error

        from pesa_logger.web3_anchor import get_anchor_summary

        try:
            return jsonify(get_anchor_summary(db_path=_db)), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        
    return app


if __name__ == "__main__":  # pragma: no cover
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("PESA_BIND_HOST", "127.0.0.1")
    app = create_app()
    app.run(host=host, port=port, debug=False)