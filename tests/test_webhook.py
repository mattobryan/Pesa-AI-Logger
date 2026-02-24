"""Tests for the webhook / API ingestion layer."""

import json
import pytest

from pesa_logger.database import close_connection, get_inbox_sms, init_db
from pesa_logger.webhook import create_app


SEND_SMS = (
    "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
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


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"


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
