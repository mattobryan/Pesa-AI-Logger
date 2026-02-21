"""Tests for the webhook / API ingestion layer."""

import json
import pytest

from pesa_logger.database import close_connection, init_db
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
        assert resp.status_code == 201  # no error on duplicate


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


class TestExportCsv:
    def test_returns_csv_content(self, client):
        resp = client.get("/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
