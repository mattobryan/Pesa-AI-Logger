"""Route tests for ledger and Web3 webhook endpoints."""

from __future__ import annotations

import hashlib
import json

import pytest

from pesa_logger.database import init_db, save_inbox_sms
from pesa_logger.web3_anchor import _store_anchor_record
from pesa_logger.webhook import create_app


_SUMMARY_KEYS = {
    "web3_enabled",
    "web3_configured",
    "anchor_every_n",
    "pending_unanchored",
    "total_anchors",
    "confirmed_anchors",
    "local_only_anchors",
    "failed_anchors",
    "latest_anchor",
    "contract_address",
    "polygon_rpc_url",
}


def _make_send_sms(tx_code: str, amount: int = 1000) -> str:
    return (
        f"{tx_code} Confirmed. Ksh{amount:,.2f} sent to JOHN DOE 0712345678 "
        "on 21/2/26 at 10:30 AM. New M-PESA balance is Ksh5,000.00. "
        "Transaction cost, Ksh14.00."
    )


def _seed_ledger_hashes(db_path: str, count: int) -> None:
    for idx in range(count):
        save_inbox_sms(
            raw_text=f"ledger seed {idx}",
            source="tests",
            db_path=db_path,
        )


def _json_post(client, path: str, payload: dict | None = None, headers: dict | None = None):
    return client.post(
        path,
        data=json.dumps(payload or {}),
        content_type="application/json",
        headers=headers or {},
    )


@pytest.fixture(autouse=True)
def clear_web3_env(monkeypatch):
    for key in (
        "WEB3_ENABLED",
        "POLYGON_RPC_URL",
        "WALLET_PRIVATE_KEY",
        "CONTRACT_ADDRESS",
        "ANCHOR_EVERY_N",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def db_path(tmp_path):
    db = str(tmp_path / "webhook_ledger.db")
    init_db(db)
    return db


@pytest.fixture()
def client(db_path):
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = db_path
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def client_with_api_key(db_path):
    app = create_app(db_path=db_path, api_key="secret123")
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = db_path
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": "secret123"}


def test_post_anchor_requires_auth(client_with_api_key):
    resp = _json_post(client_with_api_key, "/ledger/anchor")
    assert resp.status_code == 401


def test_post_anchor_rejects_wrong_key(client_with_api_key):
    resp = _json_post(client_with_api_key, "/ledger/anchor", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_post_anchor_below_threshold_returns_202(client_with_api_key, db_path, auth_headers):
    _seed_ledger_hashes(db_path, 1)
    resp = _json_post(client_with_api_key, "/ledger/anchor", headers=auth_headers)
    assert resp.status_code == 202
    payload = json.loads(resp.data)
    assert payload["anchored"] is False


def test_post_anchor_force_returns_200(client_with_api_key, db_path, auth_headers):
    _seed_ledger_hashes(db_path, 1)
    resp = _json_post(client_with_api_key, "/ledger/anchor", {"force": True}, headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["anchored"] is True
    assert payload["status"] == "web3_disabled"


def test_post_anchor_empty_db_returns_202(client_with_api_key, auth_headers):
    resp = _json_post(client_with_api_key, "/ledger/anchor", headers=auth_headers)
    assert resp.status_code == 202
    payload = json.loads(resp.data)
    assert payload["anchored"] is False


def test_post_anchor_at_threshold_returns_200(
    client_with_api_key,
    db_path,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setenv("ANCHOR_EVERY_N", "2")
    _seed_ledger_hashes(db_path, 2)
    resp = _json_post(client_with_api_key, "/ledger/anchor", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["anchored"] is True


def test_post_anchor_no_body_defaults_to_non_force(
    client_with_api_key,
    db_path,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setenv("ANCHOR_EVERY_N", "2")
    _seed_ledger_hashes(db_path, 1)
    resp = client_with_api_key.post("/ledger/anchor", headers=auth_headers)
    assert resp.status_code == 202
    payload = json.loads(resp.data)
    assert payload["anchored"] is False


def test_get_anchors_requires_auth(client_with_api_key):
    resp = client_with_api_key.get("/ledger/anchors")
    assert resp.status_code == 401


def test_get_anchors_rejects_wrong_key(client_with_api_key):
    resp = client_with_api_key.get("/ledger/anchors", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_get_anchors_empty_structure(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/anchors", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["anchors"] == []
    assert isinstance(payload["summary"], dict)


def test_get_anchors_after_anchor(client_with_api_key, db_path, auth_headers):
    _seed_ledger_hashes(db_path, 1)
    _json_post(client_with_api_key, "/ledger/anchor", {"force": True}, headers=auth_headers)
    resp = client_with_api_key.get("/ledger/anchors", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert len(payload["anchors"]) >= 1


def test_get_anchors_status_filter(client_with_api_key, db_path, auth_headers):
    _store_anchor_record(
        db_path=db_path,
        merkle_root=hashlib.sha256(b"disabled").hexdigest(),
        tx_hashes=[hashlib.sha256(b"tx-disabled").hexdigest()],
        status="web3_disabled",
    )
    _store_anchor_record(
        db_path=db_path,
        merkle_root=hashlib.sha256(b"failed").hexdigest(),
        tx_hashes=[hashlib.sha256(b"tx-failed").hexdigest()],
        status="failed",
    )
    resp = client_with_api_key.get("/ledger/anchors?status=failed", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert len(payload["anchors"]) == 1
    assert payload["anchors"][0]["status"] == "failed"


def test_get_anchors_limit_param(client_with_api_key, db_path, auth_headers):
    for idx in range(3):
        _store_anchor_record(
            db_path=db_path,
            merkle_root=hashlib.sha256(f"root-{idx}".encode("utf-8")).hexdigest(),
            tx_hashes=[hashlib.sha256(f"tx-{idx}".encode("utf-8")).hexdigest()],
            status="web3_disabled",
        )
    resp = client_with_api_key.get("/ledger/anchors?limit=2", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert len(payload["anchors"]) == 2


def test_get_anchors_summary_keys_present(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/anchors", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert _SUMMARY_KEYS.issubset(payload["summary"].keys())


def test_get_verify_onchain_requires_auth(client_with_api_key):
    resp = client_with_api_key.get("/ledger/verify-onchain")
    assert resp.status_code == 401


def test_get_verify_onchain_no_confirmed_returns_404(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/verify-onchain", headers=auth_headers)
    assert resp.status_code == 404
    payload = json.loads(resp.data)
    assert payload["verified"] is False


def test_get_verify_onchain_with_explicit_root(client_with_api_key, auth_headers, monkeypatch):
    root = "ab" * 32

    def fake_verify_onchain(merkle_root, config):
        return {
            "verified": True,
            "merkle_root": merkle_root,
            "message": "ok",
        }

    monkeypatch.setattr("pesa_logger.web3_anchor.verify_onchain", fake_verify_onchain)
    resp = client_with_api_key.get(f"/ledger/verify-onchain?root={root}", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["verified"] is True
    assert payload["merkle_root"] == root


def test_get_verify_onchain_invalid_root(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/verify-onchain?root=not-a-hex-root", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["verified"] is False


def test_get_anchor_summary_requires_auth(client_with_api_key):
    resp = client_with_api_key.get("/ledger/anchor-summary")
    assert resp.status_code == 401


def test_get_anchor_summary_required_keys(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/anchor-summary", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert _SUMMARY_KEYS.issubset(payload.keys())


def test_get_anchor_summary_web3_disabled_in_ci(client_with_api_key, auth_headers):
    resp = client_with_api_key.get("/ledger/anchor-summary", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["web3_enabled"] is False


def test_get_anchor_summary_counts_update_after_anchor(client_with_api_key, db_path, auth_headers):
    _seed_ledger_hashes(db_path, 2)
    _json_post(client_with_api_key, "/ledger/anchor", {"force": True}, headers=auth_headers)
    resp = client_with_api_key.get("/ledger/anchor-summary", headers=auth_headers)
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert payload["total_anchors"] >= 1
    assert payload["local_only_anchors"] >= 1


def test_auto_trigger_after_three_sms_at_threshold(client, monkeypatch):
    monkeypatch.setenv("ANCHOR_EVERY_N", "3")
    calls = []

    def fake_anchor_pending_transactions(db_path, config, force=False):
        calls.append(
            {
                "db_path": db_path,
                "force": force,
                "anchor_every_n": config.anchor_every_n,
            }
        )
        return {"anchored": len(calls) >= 3}

    monkeypatch.setattr(
        "pesa_logger.web3_anchor.anchor_pending_transactions",
        fake_anchor_pending_transactions,
    )

    sms_codes = ["BC47YUA", "BC47YUB", "BC47YUC"]
    for idx, code in enumerate(sms_codes):
        resp = _json_post(
            client,
            "/sms",
            {"sms": _make_send_sms(code, amount=1000 + (idx * 100))},
        )
        assert resp.status_code == 201

    assert len(calls) == 3
    assert all(call["anchor_every_n"] == 3 for call in calls)
    assert calls[-1]["force"] is False
