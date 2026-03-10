"""Unit tests for the pure-Python Web3 anchor layer."""

from __future__ import annotations

import hashlib

import pytest

from pesa_logger.database import init_db, save_inbox_sms
from pesa_logger.web3_anchor import (
    Web3Config,
    _store_anchor_record,
    anchor_pending_transactions,
    compute_merkle_root,
    get_anchor_summary,
    list_anchor_records,
    verify_merkle_proof,
)


_WEB3_ENV_KEYS = (
    "WEB3_ENABLED",
    "POLYGON_RPC_URL",
    "WALLET_PRIVATE_KEY",
    "CONTRACT_ADDRESS",
    "ANCHOR_EVERY_N",
)

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


@pytest.fixture(autouse=True)
def clear_web3_env(monkeypatch):
    for key in _WEB3_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "web3_anchor_test.db")


def _seed_ledger_hashes(db_path: str, count: int) -> None:
    init_db(db_path)
    for idx in range(count):
        save_inbox_sms(
            raw_text=f"seed message {idx}",
            source="tests",
            db_path=db_path,
        )


def _disabled_config(monkeypatch, anchor_every_n: int = 10) -> Web3Config:
    monkeypatch.setenv("WEB3_ENABLED", "false")
    monkeypatch.setenv("ANCHOR_EVERY_N", str(anchor_every_n))
    return Web3Config()


def _enabled_config(
    monkeypatch,
    anchor_every_n: int = 10,
    wallet_private_key: str = "0xabc123",
    contract_address: str = "0xdef456",
) -> Web3Config:
    monkeypatch.setenv("WEB3_ENABLED", "true")
    monkeypatch.setenv("ANCHOR_EVERY_N", str(anchor_every_n))
    monkeypatch.setenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    monkeypatch.setenv("WALLET_PRIVATE_KEY", wallet_private_key)
    monkeypatch.setenv("CONTRACT_ADDRESS", contract_address)
    return Web3Config()


def test_compute_merkle_root_single_hash():
    leaf = "ab" * 32
    assert compute_merkle_root([leaf]) == leaf


def test_compute_merkle_root_two_hashes():
    left = "11" * 32
    right = "22" * 32
    expected = hashlib.sha256(bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()
    assert compute_merkle_root([left, right]) == expected


def test_compute_merkle_root_ordering_changes_root():
    first = "01" * 32
    second = "02" * 32
    assert compute_merkle_root([first, second]) != compute_merkle_root([second, first])


def test_compute_merkle_root_odd_count_duplicates_last_leaf():
    hashes = ["10" * 32, "20" * 32, "30" * 32]
    assert compute_merkle_root(hashes) == compute_merkle_root(hashes + [hashes[-1]])


def test_compute_merkle_root_large_batch_is_stable():
    tx_hashes = [hashlib.sha256(f"tx-{idx}".encode("utf-8")).hexdigest() for idx in range(256)]
    root_once = compute_merkle_root(tx_hashes)
    root_twice = compute_merkle_root(tx_hashes)
    assert len(root_once) == 64
    assert root_once == root_twice


def test_verify_merkle_proof_single_element_tree():
    leaf = "aa" * 32
    root = compute_merkle_root([leaf])
    assert verify_merkle_proof(leaf, [], root) is True


def test_verify_merkle_proof_rejects_wrong_hash():
    leaf = "aa" * 32
    wrong_leaf = "bb" * 32
    root = compute_merkle_root([leaf])
    assert verify_merkle_proof(wrong_leaf, [], root) is False


def test_verify_merkle_proof_rejects_tampered_root():
    leaf = "aa" * 32
    root = compute_merkle_root([leaf])
    tampered_root = f"{root[:-1]}0"
    assert verify_merkle_proof(leaf, [], tampered_root) is False


def test_anchor_pending_below_threshold(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 1)
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=5),
    )
    assert result["anchored"] is False
    assert result["pending_count"] == 1
    assert result["threshold"] == 5


def test_anchor_pending_at_threshold(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=2),
    )
    assert result["anchored"] is True
    assert result["status"] == "web3_disabled"
    assert result["tx_count"] == 2


def test_anchor_pending_force_below_threshold(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 1)
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=10),
        force=True,
    )
    assert result["anchored"] is True
    assert result["status"] == "web3_disabled"
    assert result["tx_count"] == 1


def test_anchor_pending_force_empty_db_returns_no_hashes(db_path, monkeypatch):
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=10),
        force=True,
    )
    assert result["anchored"] is False
    assert "No ledger hashes" in result["message"]


def test_anchor_pending_persists_record(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=2),
    )
    assert result["anchored"] is True
    records = list_anchor_records(db_path=db_path)
    assert len(records) == 1
    assert records[0]["merkle_root"] == result["merkle_root"]
    assert records[0]["status"] == "web3_disabled"


def test_anchor_pending_duplicate_idempotency(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)

    def fake_anchor_to_polygon(_merkle_root, _config):
        raise RuntimeError("simulated polygon outage")

    monkeypatch.setattr("pesa_logger.web3_anchor._anchor_to_polygon", fake_anchor_to_polygon)
    config = _enabled_config(monkeypatch, anchor_every_n=2)
    first = anchor_pending_transactions(db_path=db_path, config=config)
    second = anchor_pending_transactions(db_path=db_path, config=config)

    assert first["anchored"] is False
    assert first["status"] == "failed"
    assert second["anchored"] is True
    assert second["status"] == "already_anchored"


def test_anchor_pending_enabled_unconfigured(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)
    monkeypatch.setenv("WEB3_ENABLED", "true")
    monkeypatch.setenv("ANCHOR_EVERY_N", "2")
    config = Web3Config()
    result = anchor_pending_transactions(db_path=db_path, config=config)
    assert result["anchored"] is False
    assert "missing" in result["message"].lower()
    assert "WALLET_PRIVATE_KEY" in result["message"]


def test_anchor_pending_enabled_success_path(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)

    def fake_anchor_to_polygon(_merkle_root, _config):
        return "0xabc", 123

    monkeypatch.setattr("pesa_logger.web3_anchor._anchor_to_polygon", fake_anchor_to_polygon)
    config = _enabled_config(monkeypatch, anchor_every_n=2)
    result = anchor_pending_transactions(db_path=db_path, config=config)

    assert result["anchored"] is True
    assert result["status"] == "confirmed"
    assert result["block_number"] == 123
    assert result["anchor_tx_hash"] == "0xabc"
    confirmed = list_anchor_records(db_path=db_path, status="confirmed")
    assert len(confirmed) == 1


def test_anchor_pending_enabled_failure_marks_record_failed(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)

    def fake_anchor_to_polygon(_merkle_root, _config):
        raise RuntimeError("rpc failure")

    monkeypatch.setattr("pesa_logger.web3_anchor._anchor_to_polygon", fake_anchor_to_polygon)
    config = _enabled_config(monkeypatch, anchor_every_n=2)
    result = anchor_pending_transactions(db_path=db_path, config=config)

    assert result["anchored"] is False
    assert result["status"] == "failed"
    failed = list_anchor_records(db_path=db_path, status="failed")
    assert len(failed) == 1


def test_anchor_pending_empty_db_below_threshold(db_path, monkeypatch):
    result = anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=3),
    )
    assert result["anchored"] is False
    assert result["pending_count"] == 0
    assert result["threshold"] == 3


def test_list_anchor_records_empty(db_path):
    assert list_anchor_records(db_path=db_path) == []


def test_list_anchor_records_populated(db_path):
    root = hashlib.sha256(b"root-a").hexdigest()
    _store_anchor_record(
        db_path=db_path,
        merkle_root=root,
        tx_hashes=[hashlib.sha256(b"tx-a").hexdigest()],
        status="web3_disabled",
    )
    rows = list_anchor_records(db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["merkle_root"] == root


def test_list_anchor_records_status_filter(db_path):
    failed_root = hashlib.sha256(b"failed-root").hexdigest()
    disabled_root = hashlib.sha256(b"disabled-root").hexdigest()
    _store_anchor_record(
        db_path=db_path,
        merkle_root=failed_root,
        tx_hashes=[hashlib.sha256(b"tx-failed").hexdigest()],
        status="failed",
    )
    _store_anchor_record(
        db_path=db_path,
        merkle_root=disabled_root,
        tx_hashes=[hashlib.sha256(b"tx-disabled").hexdigest()],
        status="web3_disabled",
    )
    rows = list_anchor_records(db_path=db_path, status="failed")
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["merkle_root"] == failed_root


def test_list_anchor_records_limit(db_path):
    for idx in range(3):
        _store_anchor_record(
            db_path=db_path,
            merkle_root=hashlib.sha256(f"root-{idx}".encode("utf-8")).hexdigest(),
            tx_hashes=[hashlib.sha256(f"tx-{idx}".encode("utf-8")).hexdigest()],
            status="web3_disabled",
        )
    rows = list_anchor_records(db_path=db_path, limit=2)
    assert len(rows) == 2


def test_get_anchor_summary_empty_db(db_path):
    summary = get_anchor_summary(db_path=db_path)
    assert _SUMMARY_KEYS.issubset(summary.keys())
    assert summary["total_anchors"] == 0
    assert summary["pending_unanchored"] == 0


def test_get_anchor_summary_after_anchor(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)
    anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=2),
    )
    summary = get_anchor_summary(db_path=db_path)
    assert summary["total_anchors"] >= 1
    assert summary["local_only_anchors"] >= 1
    assert summary["pending_unanchored"] == 0


def test_get_anchor_summary_required_keys(db_path, monkeypatch):
    _seed_ledger_hashes(db_path, 2)
    anchor_pending_transactions(
        db_path=db_path,
        config=_disabled_config(monkeypatch, anchor_every_n=2),
    )
    summary = get_anchor_summary(db_path=db_path)
    assert _SUMMARY_KEYS.issubset(summary.keys())
    assert summary["latest_anchor"] is not None


def test_web3_config_disabled_by_default():
    cfg = Web3Config()
    assert cfg.enabled is False
    assert cfg.anchor_every_n == 10
    assert cfg.is_configured is False


def test_web3_config_enabled_and_configured(monkeypatch):
    cfg = _enabled_config(monkeypatch, anchor_every_n=7)
    assert cfg.enabled is True
    assert cfg.anchor_every_n == 7
    assert cfg.is_configured is True
