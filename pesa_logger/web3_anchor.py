"""Web3 ledger anchoring for Pesa AI Logger.

Upgrades the local hash-chain ledger to a publicly verifiable system by
periodically committing a Merkle root of recent transaction hashes to the
Polygon blockchain.

Architecture
------------
The local ledger is already tamper-evident (SHA-256 hash chain stored in
SQLite). This module adds public verifiability WITHOUT exposing any
transaction data:

    Every ANCHOR_EVERY_N transactions:
      1. Collect the last N transaction hashes from the ledger
      2. Compute a Merkle root (pure Python, no external lib)
      3. Publish that single bytes32 root to the PesaAnchor smart contract
      4. Store the anchor record (root + on-chain tx hash) in ledger_anchors

Anyone can verify the ledger by:
  - Fetching the local transaction hashes
  - Recomputing the Merkle root
  - Checking the PesaAnchor contract: anchors[root] != 0

Configuration (.env)
--------------------
WEB3_ENABLED        : true | false   (default: false — safe offline mode)
POLYGON_RPC_URL     : https://polygon-rpc.com  (or Alchemy/Infura URL)
WALLET_PRIVATE_KEY  : 0x...           (deployer wallet — keep secret)
CONTRACT_ADDRESS    : 0x...           (deployed PesaAnchor contract address)
ANCHOR_EVERY_N      : 10             (anchor after every N new transactions)

When WEB3_ENABLED=false:
  - Merkle roots are still computed locally
  - Anchors are stored with status="pending_web3_disabled"
  - No on-chain calls are made (no web3 library required)

Dependencies (only needed when WEB3_ENABLED=true)
-------------------------------------------------
    pip install web3>=6.0.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Config ─────────────────────────────────────────────────────────────────


class Web3Config:
    """Loads Web3 configuration from environment variables."""

    def __init__(self) -> None:
        self.enabled: bool = os.environ.get("WEB3_ENABLED", "false").lower() in (
            "true", "1", "yes"
        )
        self.polygon_rpc_url: str = os.environ.get(
            "POLYGON_RPC_URL", "https://polygon-rpc.com"
        )
        self.wallet_private_key: str = os.environ.get("WALLET_PRIVATE_KEY", "")
        self.contract_address: str = os.environ.get("CONTRACT_ADDRESS", "")
        self.anchor_every_n: int = int(os.environ.get("ANCHOR_EVERY_N", "10"))

    @property
    def is_configured(self) -> bool:
        """True only when all required fields are present."""
        return bool(
            self.enabled
            and self.wallet_private_key
            and self.contract_address
            and self.polygon_rpc_url
        )


# ─── Merkle tree (pure Python, no external deps) ─────────────────────────────


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_merkle_root(tx_hashes: List[str]) -> str:
    """
    Compute a SHA-256 Merkle root from a list of hex transaction hashes.

    Implements standard binary Merkle tree with duplication of odd nodes.
    Returns a 64-character hex string (32 bytes).

    Parameters
    ----------
    tx_hashes : List of hex strings (transaction hashes from the ledger).

    Returns
    -------
    64-character hex Merkle root, or the hash of an empty string if the
    list is empty.
    """
    if not tx_hashes:
        return _sha256_hex(b"empty")

    def _norm(h: str) -> str:
        """Normalise to 64-char lowercase hex, stripping 0x prefix only."""
        h = h.lower()
        if h.startswith("0x"):
            h = h[2:]
        return h.zfill(64)

    layer = [_norm(h) for h in tx_hashes]

    while len(layer) > 1:
        # Pad to even length (duplicate last node)
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [
            _sha256_hex(
                bytes.fromhex(layer[i]) + bytes.fromhex(layer[i + 1])
            )
            for i in range(0, len(layer), 2)
        ]

    return layer[0]


def verify_merkle_proof(
    tx_hash: str,
    proof: List[str],
    merkle_root: str,
) -> bool:
    """
    Verify that *tx_hash* is included in a Merkle tree with *merkle_root*.

    Parameters
    ----------
    tx_hash    : The leaf hash to verify.
    proof      : Ordered list of sibling hashes from leaf to root.
    merkle_root: Expected Merkle root.

    Returns True if the computed root matches.
    """
    current = tx_hash.lower().lstrip("0x") or "0" * 64
    for sibling in proof:
        s = sibling.lower().lstrip("0x") or "0" * 64
        # Lexicographic ordering — matches the EVM convention
        if current <= s:
            current = _sha256_hex(
                bytes.fromhex(current) + bytes.fromhex(s)
            )
        else:
            current = _sha256_hex(
                bytes.fromhex(s) + bytes.fromhex(current)
            )
    return current == merkle_root.lower().lstrip("0x")


# ─── SQLite anchor store ──────────────────────────────────────────────────────

_CREATE_ANCHORS_TABLE = """
CREATE TABLE IF NOT EXISTS ledger_anchors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    merkle_root         TEXT    NOT NULL UNIQUE,
    tx_hashes_json      TEXT    NOT NULL,
    transaction_count   INTEGER NOT NULL DEFAULT 0,
    anchor_tx_hash      TEXT,           -- on-chain tx hash (NULL until confirmed)
    block_number        INTEGER,        -- Polygon block number
    polygon_scan_url    TEXT,           -- Polygonscan link
    status              TEXT    NOT NULL DEFAULT 'pending',
        -- pending | confirmed | failed | web3_disabled
    anchored_at         TEXT    NOT NULL,
    confirmed_at        TEXT
)
"""

_INDEX_ANCHORS = """
CREATE INDEX IF NOT EXISTS idx_anchors_status
    ON ledger_anchors (status);
"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_anchors_table(db_path: str) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(_CREATE_ANCHORS_TABLE)
        conn.execute(_INDEX_ANCHORS)


def _store_anchor_record(
    db_path: str,
    merkle_root: str,
    tx_hashes: List[str],
    status: str,
    anchor_tx_hash: Optional[str] = None,
    block_number: Optional[int] = None,
    polygon_scan_url: Optional[str] = None,
) -> int:
    """Insert an anchor record into ledger_anchors. Returns the new row id."""
    _ensure_anchors_table(db_path)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with _get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO ledger_anchors
                (merkle_root, tx_hashes_json, transaction_count,
                 anchor_tx_hash, block_number, polygon_scan_url,
                 status, anchored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merkle_root,
                json.dumps(tx_hashes),
                len(tx_hashes),
                anchor_tx_hash,
                block_number,
                polygon_scan_url,
                status,
                now,
            ),
        )
        return cur.lastrowid


def _update_anchor_status(
    db_path: str,
    merkle_root: str,
    status: str,
    anchor_tx_hash: Optional[str] = None,
    block_number: Optional[int] = None,
    polygon_scan_url: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE ledger_anchors
               SET status = ?,
                   anchor_tx_hash = COALESCE(?, anchor_tx_hash),
                   block_number   = COALESCE(?, block_number),
                   polygon_scan_url = COALESCE(?, polygon_scan_url),
                   confirmed_at   = ?
             WHERE merkle_root = ?
            """,
            (
                status,
                anchor_tx_hash,
                block_number,
                polygon_scan_url,
                now,
                merkle_root,
            ),
        )


def list_anchor_records(
    db_path: str,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return anchor records from newest to oldest."""
    _ensure_anchors_table(db_path)
    with _get_conn(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM ledger_anchors WHERE status = ? "
                "ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ledger_anchors ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


# ─── Ledger hash fetching ─────────────────────────────────────────────────────


def _fetch_unanchored_hashes(
    db_path: str, limit: int
) -> List[str]:
    """
    Fetch up to *limit* ledger event hashes that have not yet been anchored.

    Reads from the append-only hash-chain ledger.
    Prefer `ledger_chain` (current schema), fall back to `ledger_events`
    for backward compatibility.
    Returns hashes in chronological order.
    """
    _ensure_anchors_table(db_path)
    with _get_conn(db_path) as conn:
        # Simpler approach: count how many hashes are in all confirmed anchors
        total_anchored_rows = conn.execute(
            "SELECT COALESCE(SUM(transaction_count), 0) FROM ledger_anchors "
            "WHERE status IN ('confirmed', 'web3_disabled')"
        ).fetchone()[0]

        try:
            rows = conn.execute(
                """
                SELECT event_hash FROM ledger_chain
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, total_anchored_rows),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            # Backward compatibility for older database schema names.
            if "no such table" not in str(exc).lower():
                raise
            rows = conn.execute(
                """
                SELECT event_hash FROM ledger_events
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, total_anchored_rows),
            ).fetchall()

    return [r[0] for r in rows if r[0]]


def _count_pending_anchor_hashes(db_path: str) -> int:
    """Count ledger hashes not yet anchored."""
    _ensure_anchors_table(db_path)
    with _get_conn(db_path) as conn:
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM ledger_chain"
            ).fetchone()[0]
        except sqlite3.OperationalError as exc:
            # Backward compatibility for older database schema names.
            if "no such table" not in str(exc).lower():
                raise
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM ledger_events"
                ).fetchone()[0]
            except sqlite3.OperationalError as legacy_exc:
                if "no such table" not in str(legacy_exc).lower():
                    raise
                total = 0
        anchored = conn.execute(
            "SELECT COALESCE(SUM(transaction_count), 0) FROM ledger_anchors "
            "WHERE status IN ('confirmed', 'web3_disabled')"
        ).fetchone()[0]
    return max(0, total - anchored)


# ─── On-chain anchoring ───────────────────────────────────────────────────────


def _build_polygon_scan_url(tx_hash: str, mainnet: bool = True) -> str:
    base = "https://polygonscan.com/tx" if mainnet else "https://mumbai.polygonscan.com/tx"
    return f"{base}/{tx_hash}"


def _anchor_to_polygon(
    merkle_root: str,
    config: Web3Config,
) -> Tuple[str, int]:
    """
    Submit a Merkle root to the PesaAnchor smart contract on Polygon.

    Returns (tx_hash, block_number).
    Raises RuntimeError on any failure.
    """
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
    except ImportError as exc:
        raise ImportError(
            "web3 package is required when WEB3_ENABLED=true. "
            "Install it with: pip install web3>=6.0.0"
        ) from exc

    w3 = Web3(Web3.HTTPProvider(config.polygon_rpc_url))
    # Polygon PoS is a PoA chain — inject the middleware
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        raise RuntimeError(
            f"Cannot connect to Polygon RPC: {config.polygon_rpc_url}"
        )

    account = w3.eth.account.from_key(config.wallet_private_key)

    # Minimal ABI — only the anchor() function needed
    abi = [
        {
            "inputs": [{"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"}],
            "name": "anchor",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(config.contract_address),
        abi=abi,
    )

    # Convert hex root string to bytes32
    root_bytes = bytes.fromhex(merkle_root.lstrip("0x").zfill(64))

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    txn = contract.functions.anchor(root_bytes).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 80_000,
        "gasPrice": gas_price,
        "chainId": 137,  # Polygon mainnet
    })

    signed = account.sign_transaction(txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] != 1:
        raise RuntimeError(
            f"Anchor transaction reverted. Hash: {tx_hash.hex()}"
        )

    return tx_hash.hex(), receipt["blockNumber"]


# ─── Public API ───────────────────────────────────────────────────────────────


def anchor_pending_transactions(
    db_path: str = "pesa_logger.db",
    config: Optional[Web3Config] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Check if enough unanchored transactions have accumulated and anchor them.

    This is the main entry point — call it after every SMS ingest or on demand.

    Parameters
    ----------
    db_path : SQLite database path.
    config  : Web3Config (loaded from env if None).
    force   : If True, anchor even if fewer than ANCHOR_EVERY_N are pending.

    Returns
    -------
    Dict with keys: anchored (bool), merkle_root, tx_count, status, message.
    """
    if config is None:
        config = Web3Config()

    pending_count = _count_pending_anchor_hashes(db_path)

    if not force and pending_count < config.anchor_every_n:
        return {
            "anchored": False,
            "pending_count": pending_count,
            "threshold": config.anchor_every_n,
            "message": f"{pending_count}/{config.anchor_every_n} transactions pending — threshold not reached",
        }

    batch_size = config.anchor_every_n if not force else max(pending_count, 1)
    tx_hashes = _fetch_unanchored_hashes(db_path, batch_size)

    if not tx_hashes:
        return {
            "anchored": False,
            "message": "No ledger hashes available to anchor",
            "pending_count": 0,
        }

    merkle_root = compute_merkle_root(tx_hashes)

    if not config.enabled:
        # Store locally with disabled status — no on-chain call
        _store_anchor_record(
            db_path=db_path,
            merkle_root=merkle_root,
            tx_hashes=tx_hashes,
            status="web3_disabled",
        )
        return {
            "anchored": True,
            "merkle_root": merkle_root,
            "tx_count": len(tx_hashes),
            "status": "web3_disabled",
            "message": (
                "Merkle root computed locally. "
                "Set WEB3_ENABLED=true in .env to publish on-chain."
            ),
        }

    if not config.is_configured:
        missing = []
        if not config.wallet_private_key:
            missing.append("WALLET_PRIVATE_KEY")
        if not config.contract_address:
            missing.append("CONTRACT_ADDRESS")
        return {
            "anchored": False,
            "merkle_root": merkle_root,
            "message": f"WEB3_ENABLED=true but missing: {', '.join(missing)}",
        }

    # Store as pending before the on-chain call (idempotent on duplicate root)
    try:
        _store_anchor_record(
            db_path=db_path,
            merkle_root=merkle_root,
            tx_hashes=tx_hashes,
            status="pending",
        )
    except sqlite3.IntegrityError:
        # Already anchored — root already in table (UNIQUE constraint)
        return {
            "anchored": True,
            "merkle_root": merkle_root,
            "tx_count": len(tx_hashes),
            "status": "already_anchored",
            "message": "This Merkle root was already anchored.",
        }

    # Submit to Polygon
    try:
        tx_hash, block_number = _anchor_to_polygon(merkle_root, config)
        scan_url = _build_polygon_scan_url(tx_hash)

        _update_anchor_status(
            db_path=db_path,
            merkle_root=merkle_root,
            status="confirmed",
            anchor_tx_hash=tx_hash,
            block_number=block_number,
            polygon_scan_url=scan_url,
        )

        logger.info(
            "Anchored %d hashes to Polygon. Root: %s Block: %d",
            len(tx_hashes), merkle_root[:16] + "…", block_number,
        )

        return {
            "anchored": True,
            "merkle_root": merkle_root,
            "tx_count": len(tx_hashes),
            "anchor_tx_hash": tx_hash,
            "block_number": block_number,
            "polygon_scan_url": scan_url,
            "status": "confirmed",
            "message": f"Successfully anchored to Polygon block {block_number}.",
        }

    except Exception as exc:  # noqa: BLE001
        _update_anchor_status(db_path=db_path, merkle_root=merkle_root, status="failed")
        logger.error("Failed to anchor to Polygon: %s", exc)
        return {
            "anchored": False,
            "merkle_root": merkle_root,
            "tx_count": len(tx_hashes),
            "status": "failed",
            "error": str(exc),
            "message": "Merkle root stored locally. On-chain submission failed.",
        }


def verify_onchain(
    merkle_root: str,
    config: Optional[Web3Config] = None,
) -> Dict[str, Any]:
    """
    Verify that a Merkle root is recorded on the Polygon PesaAnchor contract.

    Returns dict with: verified (bool), block_number, message.
    """
    if config is None:
        config = Web3Config()

    if not config.enabled:
        return {
            "verified": False,
            "message": "WEB3_ENABLED=false — on-chain verification unavailable.",
        }

    if not config.is_configured:
        return {
            "verified": False,
            "message": "Web3 not fully configured. Check WALLET_PRIVATE_KEY and CONTRACT_ADDRESS.",
        }

    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
    except ImportError:
        return {
            "verified": False,
            "message": "web3 package not installed. Run: pip install web3>=6.0.0",
        }

    try:
        w3 = Web3(Web3.HTTPProvider(config.polygon_rpc_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        abi = [
            {
                "inputs": [{"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"}],
                "name": "verify",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
                "name": "anchors",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
        ]

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(config.contract_address),
            abi=abi,
        )

        root_bytes = bytes.fromhex(merkle_root.lstrip("0x").zfill(64))
        block_number = contract.functions.anchors(root_bytes).call()

        if block_number > 0:
            return {
                "verified": True,
                "merkle_root": merkle_root,
                "block_number": block_number,
                "polygon_scan_url": f"https://polygonscan.com/block/{block_number}",
                "message": f"Root verified on-chain at Polygon block {block_number}.",
            }
        else:
            return {
                "verified": False,
                "merkle_root": merkle_root,
                "message": "Root not found on-chain. Has not been anchored yet.",
            }

    except Exception as exc:  # noqa: BLE001
        return {
            "verified": False,
            "error": str(exc),
            "message": f"On-chain verification failed: {exc}",
        }


def get_anchor_summary(db_path: str = "pesa_logger.db") -> Dict[str, Any]:
    """Return a summary of anchor status for the dashboard."""
    _ensure_anchors_table(db_path)
    records = list_anchor_records(db_path, limit=100)
    config = Web3Config()
    pending = _count_pending_anchor_hashes(db_path)

    confirmed = [r for r in records if r["status"] == "confirmed"]
    disabled = [r for r in records if r["status"] == "web3_disabled"]
    failed = [r for r in records if r["status"] == "failed"]

    latest = records[0] if records else None

    return {
        "web3_enabled": config.enabled,
        "web3_configured": config.is_configured,
        "anchor_every_n": config.anchor_every_n,
        "pending_unanchored": pending,
        "total_anchors": len(records),
        "confirmed_anchors": len(confirmed),
        "local_only_anchors": len(disabled),
        "failed_anchors": len(failed),
        "latest_anchor": latest,
        "contract_address": config.contract_address or None,
        "polygon_rpc_url": config.polygon_rpc_url if config.enabled else None,
    }
