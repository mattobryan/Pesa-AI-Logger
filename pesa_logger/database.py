"""SQLite database layer for transaction storage."""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from pesa_logger.parser import Transaction


_DEFAULT_DB = "pesa_logger.db"
_local = threading.local()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Return (and cache) a thread-local SQLite connection."""
    if not hasattr(_local, "connections"):
        _local.connections = {}
    if db_path not in _local.connections:
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connections[db_path] = conn
    return _local.connections[db_path]


@contextmanager
def _cursor(db_path: str) -> Iterator[sqlite3.Cursor]:
    conn = _get_connection(db_path)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ─── Schema ──────────────────────────────────────────────────────────────────

_CREATE_TRANSACTIONS = """
CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id    TEXT NOT NULL UNIQUE,
    type              TEXT NOT NULL,
    amount            REAL NOT NULL,
    currency          TEXT NOT NULL DEFAULT 'KES',
    counterparty_name TEXT,
    counterparty_phone TEXT,
    account_number    TEXT,
    balance           REAL,
    transaction_cost  REAL,
    timestamp         TEXT,
    category          TEXT,
    tags              TEXT,
    raw_sms           TEXT,
    created_at        TEXT NOT NULL
)
"""


def init_db(db_path: str = _DEFAULT_DB) -> None:
    """Create database schema if it does not already exist."""
    with _cursor(db_path) as cur:
        cur.execute(_CREATE_TRANSACTIONS)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def save_transaction(tx: Transaction, db_path: str = _DEFAULT_DB) -> int:
    """Persist a :class:`Transaction` and return its row id.

    Duplicate ``transaction_id`` values are silently ignored (idempotent).
    """
    init_db(db_path)
    tags_str = ",".join(tx.tags) if tx.tags else ""
    ts_str = tx.timestamp.isoformat() if tx.timestamp else None

    with _cursor(db_path) as cur:
        cur.execute(
            """
            INSERT OR IGNORE INTO transactions
            (transaction_id, type, amount, currency, counterparty_name,
             counterparty_phone, account_number, balance, transaction_cost,
             timestamp, category, tags, raw_sms, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tx.transaction_id,
                tx.type,
                tx.amount,
                tx.currency,
                tx.counterparty_name,
                tx.counterparty_phone,
                tx.account_number,
                tx.balance,
                tx.transaction_cost,
                ts_str,
                tx.category,
                tags_str,
                tx.raw_sms,
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            ),
        )
        return cur.lastrowid or 0


def get_transaction(transaction_id: str, db_path: str = _DEFAULT_DB) -> Optional[dict]:
    """Fetch a single transaction by its M-Pesa transaction ID."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_transactions(
    db_path: str = _DEFAULT_DB,
    tx_type: Optional[str] = None,
    category: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 500,
) -> List[dict]:
    """Return a list of transactions filtered by optional criteria."""
    init_db(db_path)
    query = "SELECT * FROM transactions WHERE 1=1"
    params: list = []

    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)
    if category:
        query += " AND category = ?"
        params.append(category)
    if since:
        query += " AND timestamp >= ?"
        params.append(since.isoformat())
    if until:
        query += " AND timestamp <= ?"
        params.append(until.isoformat())

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _cursor(db_path) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def update_category(
    transaction_id: str, category: str, db_path: str = _DEFAULT_DB
) -> None:
    """Update the category field for a given transaction."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "UPDATE transactions SET category = ? WHERE transaction_id = ?",
            (category, transaction_id),
        )


def delete_transaction(transaction_id: str, db_path: str = _DEFAULT_DB) -> None:
    """Delete a transaction by its M-Pesa transaction ID."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,)
        )


def close_connection(db_path: str = _DEFAULT_DB) -> None:
    """Close and remove the cached connection for *db_path*."""
    if hasattr(_local, "connections") and db_path in _local.connections:
        _local.connections[db_path].close()
        del _local.connections[db_path]
