"""Tests for the webhook / API ingestion layer."""

import json
import pytest

from pesa_logger.database import close_connection, get_inbox_sms, init_db
from pesa_logger.webhook import create_app


SEND_SMS = (
    "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)
SEND_SMS_2 = (
    "BC47YUJ Confirmed. Ksh800.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:35 AM."
    " New M-PESA balance is Ksh4,200.00. Transaction cost, Ksh10.00."
)


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "webhook_test.db")
    init_db(db_path)
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = db_path
    with app.test_client() as client:
        yield client
    close_connection(db_path)


@pytest.fixture()
def client_with_api_key(tmp_path):
    db_path = str(tmp_path / "webhook_test_api_key.db")
    init_db(db_path)
    app = create_app(db_path=db_path, api_key="secret123")
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = db_path
    with app.test_client() as client:
        yield client
    close_connection(db_path)


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert data["api_key_required"] is False

    def test_health_reports_api_key_requirement(self, client_with_api_key):
        resp = client_with_api_key.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["api_key_required"] is True


class TestIngestSms:
    def test_ingest_valid_sms_json(self, client):
        resp = client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["status"] == "saved"
        assert data["transaction"]["type"] == "send"
        assert data["transaction"]["amount"] == 1000.0

    def test_ingest_valid_sms_plain_text(self, client):
        resp = client.post("/sms", data=SEND_SMS, content_type="text/plain")
        assert resp.status_code == 201

    def test_ingest_empty_body_returns_400(self, client):
        resp = client.post(
            "/sms",
            data=json.dumps({"sms": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_ingest_invalid_sms_returns_422(self, client):
        resp = client.post(
            "/sms",
            data=json.dumps({"sms": "Hello, this is not an MPESA message"}),
            content_type="application/json",
        )
        assert resp.status_code == 422
        data = json.loads(resp.data)
        assert data["status"] == "failed"

    def test_idempotent_duplicate(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        resp = client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "duplicate"

    def test_ingest_with_meta_stamps_source(self, client):
        resp = client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": SEND_SMS,
                    "source": "android-termux",
                    "meta": {
                        "sender": "MPESA",
                        "sim_slot": "2",
                    },
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        payload = json.loads(resp.data)
        inbox = get_inbox_sms(
            inbox_id=payload["inbox_id"],
            db_path=client.application.config["TEST_DB_PATH"],
        )
        assert "android-termux" in inbox["source"]
        assert "sim:2" in inbox["source"]
        assert "sender:MPESA" in inbox["source"]

    def test_ingest_requires_api_key_when_configured(self, client_with_api_key):
        no_key = client_with_api_key.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        assert no_key.status_code == 401

        bad_key = client_with_api_key.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
            headers={"X-API-Key": "wrong"},
        )
        assert bad_key.status_code == 401

        ok = client_with_api_key.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
            headers={"X-API-Key": "secret123"},
        )
        assert ok.status_code == 201


class TestListTransactions:
    def test_returns_list(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        resp = client.get("/transactions")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filters_transactions_by_sim_slot(self, client):
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": SEND_SMS,
                    "source": "android-termux",
                    "meta": {"sim_slot": "1", "sender": "MPESA"},
                }
            ),
            content_type="application/json",
        )
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": SEND_SMS_2,
                    "source": "android-termux",
                    "meta": {"sim_slot": "2", "sender": "MPESA"},
                }
            ),
            content_type="application/json",
        )
        resp = client.get("/transactions?sim_slot=2&limit=10")
        assert resp.status_code == 200
        rows = json.loads(resp.data)
        assert len(rows) == 1
        assert rows[0]["transaction_id"] == "BC47YUJ"
        assert rows[0]["sim_slot"] == "2"


class TestInbox:
    def test_returns_raw_inbox_rows(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        resp = client.get("/inbox?limit=10&oldest_first=1")
        assert resp.status_code == 200
        rows = json.loads(resp.data)
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert "raw_text" in rows[0]

    def test_filters_inbox_by_parse_status(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": "not mpesa"}),
            content_type="application/json",
        )
        resp = client.get("/inbox?parse_status=failed&limit=10")
        assert resp.status_code == 200
        rows = json.loads(resp.data)
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert all(row.get("parse_status") == "failed" for row in rows)

    def test_filters_inbox_by_sim_slot(self, client):
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": SEND_SMS,
                    "source": "android-termux",
                    "meta": {"sim_slot": "1", "sender": "MPESA"},
                }
            ),
            content_type="application/json",
        )
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": SEND_SMS_2,
                    "source": "android-termux",
                    "meta": {"sim_slot": "2", "sender": "MPESA"},
                }
            ),
            content_type="application/json",
        )

        resp = client.get("/inbox?sim_slot=1&limit=10")
        assert resp.status_code == 200
        rows = json.loads(resp.data)
        assert len(rows) == 1
        assert rows[0]["sim_slot"] == "1"

    def test_failed_inbox_report_endpoint(self, client):
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": (
                        "RDG6CIQWO4 Confirmed. Fuliza M-PESA amount is Ksh 60.00. "
                        "Interest charged Ksh 0.60. Total Fuliza M-PESA outstanding "
                        "amount is Ksh 309.33 due on 16/05/23."
                    )
                }
            ),
            content_type="application/json",
        )
        client.post(
            "/sms",
            data=json.dumps(
                {
                    "sms": (
                        "RIC2JWGDRA confirmed.You bought Ksh100.00 of airtime on 12/9/23 at "
                        "10:11 AM.New M-PESA balance is Ksh21,606.97."
                    )
                }
            ),
            content_type="application/json",
        )

        resp = client.get("/inbox/failed/report?limit=100&sample_size=2")
        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert payload["status"] == "ok"
        assert payload["scanned_failed_rows"] >= 2
        classes = {item["class"] for item in payload["classes"]}
        assert "fuliza_drawdown_notice" in classes
        assert "airtime_purchase_receipt" in classes


class TestExportCsv:
    def test_returns_csv_content(self, client):
        resp = client.get("/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type


class TestMonitoring:
    def test_heartbeat_endpoint_returns_payload(self, client):
        resp = client.get("/monitor/heartbeat?threshold_hours=24")
        assert resp.status_code in (200, 503)
        data = json.loads(resp.data)
        assert "status" in data
        assert "alert" in data


class TestCorrections:
    def test_apply_and_list_correction(self, client):
        ingest = client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        assert ingest.status_code == 201

        resp = client.post(
            "/corrections",
            data=json.dumps(
                {
                    "transaction_id": "BC47YUI",
                    "updates": {"category": "Utilities"},
                    "reason": "manual recategorization",
                    "corrected_by": "test",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] in ("updated", "no_change")

        list_resp = client.get("/corrections?transaction_id=BC47YUI")
        assert list_resp.status_code == 200
        rows = json.loads(list_resp.data)
        assert isinstance(rows, list)


class TestLedger:
    def test_verify_ledger(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        resp = client.get("/ledger/verify")
        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert payload["valid"] is True
        assert payload["event_count"] >= 2

    def test_list_ledger_events(self, client):
        client.post(
            "/sms",
            data=json.dumps({"sms": SEND_SMS}),
            content_type="application/json",
        )
        resp = client.get("/ledger/events?limit=5")
        assert resp.status_code == 200
        rows = json.loads(resp.data)
        assert isinstance(rows, list)
        assert len(rows) >= 1
