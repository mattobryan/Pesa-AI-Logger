"""SQLite database layer for raw SMS capture and canonical transaction storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
from zoneinfo import ZoneInfo

from pesa_logger.parser import PARSER_VERSION, Transaction


_DEFAULT_DB = "pesa_logger.db"
_local = threading.local()
_NAIROBI_TZ = ZoneInfo("Africa/Nairobi")
_VALID_PARSE_STATUSES = {"pending", "success", "failed", "duplicate"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


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


def normalize_sms_text(raw_text: str) -> str:
    """Normalize raw SMS text for deterministic dedupe hashing."""
    return " ".join((raw_text or "").strip().lower().split())


def sms_hash(raw_text: str) -> str:
    """Return SHA-256 hash for a normalized SMS body."""
    return hashlib.sha256(normalize_sms_text(raw_text).encode("utf-8")).hexdigest()


def _event_time_to_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Convert event timestamps to UTC; naive values are assumed Africa/Nairobi."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_NAIROBI_TZ)
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _query_time_to_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Convert query bounds to UTC; naive values are treated as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _row_to_compat_dict(row: sqlite3.Row) -> dict:
    """Map canonical schema fields to legacy key names for compatibility."""
    data = dict(row)

    data["timestamp"] = data.get("event_time_utc")
    data["counterparty_name"] = data.get("name")
    data["counterparty_phone"] = data.get("phone")
    data["account_number"] = data.get("account_reference")
    data["transaction_cost"] = data.get("fee")

    tags_json = data.get("tags_json")
    tags_csv = ""
    if isinstance(tags_json, str) and tags_json:
        try:
            parsed = json.loads(tags_json)
            if isinstance(parsed, list):
                tags_csv = ",".join(str(tag) for tag in parsed)
            else:
                tags_csv = str(parsed)
        except json.JSONDecodeError:
            tags_csv = tags_json
    data["tags"] = tags_csv

    return data


# ─── Schema ──────────────────────────────────────────────────────────────────

_CREATE_INBOX_SMS = """
CREATE TABLE IF NOT EXISTS inbox_sms (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc   TEXT NOT NULL,
    source            TEXT NOT NULL,
    raw_text          TEXT NOT NULL,
    normalized_hash   TEXT NOT NULL UNIQUE,
    parse_status      TEXT NOT NULL CHECK (parse_status IN ('pending', 'success', 'failed', 'duplicate')),
    parse_error       TEXT,
    parser_version    TEXT,
    created_at_utc    TEXT NOT NULL
)
"""

_CREATE_TRANSACTIONS = """
CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id    TEXT,
    event_time_utc    TEXT,
    type              TEXT NOT NULL,
    amount            REAL NOT NULL,
    currency          TEXT NOT NULL DEFAULT 'KES',
    name              TEXT,
    phone             TEXT,
    account_reference TEXT,
    balance           REAL,
    fee               REAL,
    category          TEXT,
    tags_json         TEXT,
    anomaly_score     REAL,
    raw_sms_id        INTEGER NOT NULL UNIQUE,
    normalized_hash   TEXT NOT NULL,
    parser_version    TEXT,
    raw_sms           TEXT,
    created_at_utc    TEXT NOT NULL,
    FOREIGN KEY(raw_sms_id) REFERENCES inbox_sms(id)
)
"""

_CREATE_REPORT_RUNS = """
CREATE TABLE IF NOT EXISTS report_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type       TEXT NOT NULL,
    period_start_utc  TEXT,
    period_end_utc    TEXT,
    tz                TEXT NOT NULL,
    output_path       TEXT,
    created_at_utc    TEXT NOT NULL
)
"""

_CREATE_HEARTBEAT_CHECKS = """
CREATE TABLE IF NOT EXISTS heartbeat_checks (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at_utc        TEXT NOT NULL,
    last_sms_received_utc TEXT,
    silence_hours         REAL,
    threshold_hours       REAL NOT NULL,
    status                TEXT NOT NULL,
    alert_message         TEXT,
    created_at_utc        TEXT NOT NULL
)
"""

_CREATE_TRANSACTION_CORRECTIONS = """
CREATE TABLE IF NOT EXISTS transaction_corrections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id   TEXT NOT NULL,
    field_name       TEXT NOT NULL,
    old_value        TEXT,
    new_value        TEXT,
    reason           TEXT NOT NULL,
    corrected_by     TEXT NOT NULL,
    corrected_at_utc TEXT NOT NULL,
    created_at_utc   TEXT NOT NULL
)
"""

_CREATE_TXN_ID_UNIQUE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_transaction_id_not_null
ON transactions(transaction_id)
WHERE transaction_id IS NOT NULL
"""

_CREATE_HASH_FALLBACK_UNIQUE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_normalized_hash_when_no_tid
ON transactions(normalized_hash)
WHERE transaction_id IS NULL
"""

_CREATE_INBOX_HASH_IDX = """
CREATE INDEX IF NOT EXISTS ix_inbox_sms_received_at
ON inbox_sms(received_at_utc)
"""

_CREATE_TXN_EVENT_IDX = """
CREATE INDEX IF NOT EXISTS ix_transactions_event_time
ON transactions(event_time_utc)
"""

_CREATE_CORRECTIONS_TXN_IDX = """
CREATE INDEX IF NOT EXISTS ix_transaction_corrections_transaction_id
ON transaction_corrections(transaction_id)
"""


def init_db(db_path: str = _DEFAULT_DB) -> None:
    """Create database schema if it does not already exist."""
    with _cursor(db_path) as cur:
        cur.execute(_CREATE_INBOX_SMS)
        cur.execute(_CREATE_TRANSACTIONS)
        cur.execute(_CREATE_REPORT_RUNS)
        cur.execute(_CREATE_HEARTBEAT_CHECKS)
        cur.execute(_CREATE_TRANSACTION_CORRECTIONS)
        cur.execute(_CREATE_TXN_ID_UNIQUE_IDX)
        cur.execute(_CREATE_HASH_FALLBACK_UNIQUE_IDX)
        cur.execute(_CREATE_INBOX_HASH_IDX)
        cur.execute(_CREATE_TXN_EVENT_IDX)
        cur.execute(_CREATE_CORRECTIONS_TXN_IDX)


# ─── Inbox (Raw SMS) ─────────────────────────────────────────────────────────

def save_inbox_sms(
    raw_text: str,
    source: str = "unknown",
    parser_version: Optional[str] = None,
    db_path: str = _DEFAULT_DB,
) -> dict:
    """Persist a raw SMS message; return row data plus duplicate marker."""
    init_db(db_path)

    cleaned = (raw_text or "").strip()
    if not cleaned:
        raise ValueError("Cannot save empty SMS content")

    normalized_hash = sms_hash(cleaned)
    now = _utc_now_iso()
    duplicate = False
    row_id = 0

    with _cursor(db_path) as cur:
        try:
            cur.execute(
                """
                INSERT INTO inbox_sms
                (received_at_utc, source, raw_text, normalized_hash,
                 parse_status, parse_error, parser_version, created_at_utc)
                VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (
                    now,
                    source,
                    cleaned,
                    normalized_hash,
                    parser_version or PARSER_VERSION,
                    now,
                ),
            )
            row_id = cur.lastrowid or 0
        except sqlite3.IntegrityError:
            duplicate = True

    with _cursor(db_path) as cur:
        if duplicate:
            cur.execute(
                "SELECT * FROM inbox_sms WHERE normalized_hash = ?",
                (normalized_hash,),
            )
        else:
            cur.execute("SELECT * FROM inbox_sms WHERE id = ?", (row_id,))
        row = cur.fetchone()

    if not row:
        raise RuntimeError("Failed to fetch inbox_sms row after insert/select")

    result = dict(row)
    result["duplicate"] = duplicate
    return result


def get_inbox_sms(
    inbox_id: Optional[int] = None,
    normalized_hash: Optional[str] = None,
    db_path: str = _DEFAULT_DB,
) -> Optional[dict]:
    """Fetch a raw SMS row by ID or normalized hash."""
    init_db(db_path)
    if inbox_id is None and normalized_hash is None:
        raise ValueError("Provide inbox_id or normalized_hash")

    with _cursor(db_path) as cur:
        if inbox_id is not None:
            cur.execute("SELECT * FROM inbox_sms WHERE id = ?", (inbox_id,))
        else:
            cur.execute(
                "SELECT * FROM inbox_sms WHERE normalized_hash = ?",
                (normalized_hash,),
            )
        row = cur.fetchone()
        return dict(row) if row else None


def update_inbox_parse_status(
    inbox_id: int,
    parse_status: str,
    parse_error: Optional[str] = None,
    parser_version: Optional[str] = None,
    db_path: str = _DEFAULT_DB,
) -> None:
    """Update parsing state for a raw SMS row."""
    init_db(db_path)
    if parse_status not in _VALID_PARSE_STATUSES:
        raise ValueError(f"Unsupported parse_status: {parse_status}")

    with _cursor(db_path) as cur:
        cur.execute(
            """
            UPDATE inbox_sms
               SET parse_status = ?,
                   parse_error = ?,
                   parser_version = COALESCE(?, parser_version)
             WHERE id = ?
            """,
            (parse_status, parse_error, parser_version, inbox_id),
        )


# ─── Transactions (Canonical Ledger) ────────────────────────────────────────

def save_transaction(
    tx: Transaction,
    db_path: str = _DEFAULT_DB,
    raw_sms_id: Optional[int] = None,
    normalized_hash: Optional[str] = None,
    parser_version: Optional[str] = None,
    anomaly_score: Optional[float] = None,
) -> int:
    """Persist a transaction and return its row id; duplicates return 0."""
    init_db(db_path)

    if raw_sms_id is None:
        # Backward-compatible path for older callers.
        raw_for_inbox = (tx.raw_sms or "").strip()
        if tx.transaction_id and tx.transaction_id not in raw_for_inbox:
            raw_for_inbox = f"{raw_for_inbox} [tid:{tx.transaction_id}]".strip()
        if not raw_for_inbox:
            raw_for_inbox = f"{tx.transaction_id} {tx.type} {tx.amount}"

        inbox_row = save_inbox_sms(
            raw_text=raw_for_inbox,
            source="internal",
            parser_version=parser_version or PARSER_VERSION,
            db_path=db_path,
        )
        raw_sms_id = int(inbox_row["id"])
        normalized_hash = normalized_hash or str(inbox_row["normalized_hash"])

    normalized_hash = normalized_hash or sms_hash(tx.raw_sms or str(raw_sms_id))
    tx_id = (tx.transaction_id or "").strip() or None
    tags_json = json.dumps(tx.tags or [], ensure_ascii=True)
    event_time_utc = _event_time_to_utc_iso(tx.timestamp)
    created_at_utc = _utc_now_iso()

    with _cursor(db_path) as cur:
        cur.execute(
            """
            INSERT OR IGNORE INTO transactions
            (transaction_id, event_time_utc, type, amount, currency, name, phone,
             account_reference, balance, fee, category, tags_json, anomaly_score,
             raw_sms_id, normalized_hash, parser_version, raw_sms, created_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tx_id,
                event_time_utc,
                tx.type,
                tx.amount,
                tx.currency,
                tx.counterparty_name,
                tx.counterparty_phone,
                tx.account_number,
                tx.balance,
                tx.transaction_cost,
                tx.category,
                tags_json,
                anomaly_score,
                raw_sms_id,
                normalized_hash,
                parser_version or getattr(tx, "parser_version", PARSER_VERSION),
                tx.raw_sms,
                created_at_utc,
            ),
        )
        return cur.lastrowid or 0


def get_transaction(transaction_id: str, db_path: str = _DEFAULT_DB) -> Optional[dict]:
    """Fetch a single transaction by its M-Pesa transaction ID."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = cur.fetchone()
        return _row_to_compat_dict(row) if row else None


def get_transaction_by_raw_sms_id(
    raw_sms_id: int,
    db_path: str = _DEFAULT_DB,
) -> Optional[dict]:
    """Fetch a canonical transaction by the source inbox_sms row id."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute("SELECT * FROM transactions WHERE raw_sms_id = ?", (raw_sms_id,))
        row = cur.fetchone()
        return _row_to_compat_dict(row) if row else None


def list_transactions(
    db_path: str = _DEFAULT_DB,
    tx_type: Optional[str] = None,
    category: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 500,
) -> List[dict]:
    """Return transactions filtered by optional criteria."""
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
        query += " AND event_time_utc >= ?"
        params.append(_query_time_to_utc_iso(since))
    if until:
        query += " AND event_time_utc <= ?"
        params.append(_query_time_to_utc_iso(until))

    query += " ORDER BY event_time_utc DESC, id DESC LIMIT ?"
    params.append(limit)

    with _cursor(db_path) as cur:
        cur.execute(query, params)
        return [_row_to_compat_dict(row) for row in cur.fetchall()]


def update_category(
    transaction_id: str,
    category: str,
    db_path: str = _DEFAULT_DB,
) -> None:
    """Update category for a given transaction_id."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "UPDATE transactions SET category = ? WHERE transaction_id = ?",
            (category, transaction_id),
        )


def delete_transaction(transaction_id: str, db_path: str = _DEFAULT_DB) -> None:
    """Delete a transaction by transaction_id."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            "DELETE FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        )


# ─── Report Run Tracking ─────────────────────────────────────────────────────

def log_report_run(
    report_type: str,
    db_path: str = _DEFAULT_DB,
    period_start_utc: Optional[str] = None,
    period_end_utc: Optional[str] = None,
    tz: str = "Africa/Nairobi",
    output_path: Optional[str] = None,
) -> int:
    """Persist report generation metadata."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO report_runs
            (report_type, period_start_utc, period_end_utc, tz, output_path, created_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                report_type,
                period_start_utc,
                period_end_utc,
                tz,
                output_path,
                _utc_now_iso(),
            ),
        )
        return cur.lastrowid or 0


def get_last_sms_received_utc(db_path: str = _DEFAULT_DB) -> Optional[str]:
    """Return the latest inbox_sms received timestamp (UTC ISO string)."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute("SELECT MAX(received_at_utc) AS last_ts FROM inbox_sms")
        row = cur.fetchone()
        if not row:
            return None
        return row["last_ts"]


def log_heartbeat_check(
    status: str,
    threshold_hours: float,
    db_path: str = _DEFAULT_DB,
    last_sms_received_utc: Optional[str] = None,
    silence_hours: Optional[float] = None,
    alert_message: Optional[str] = None,
) -> int:
    """Persist heartbeat/silence-check telemetry."""
    init_db(db_path)
    now = _utc_now_iso()
    with _cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO heartbeat_checks
            (checked_at_utc, last_sms_received_utc, silence_hours,
             threshold_hours, status, alert_message, created_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                last_sms_received_utc,
                silence_hours,
                threshold_hours,
                status,
                alert_message,
                now,
            ),
        )
        return cur.lastrowid or 0


def list_heartbeat_checks(
    db_path: str = _DEFAULT_DB,
    limit: int = 100,
) -> List[dict]:
    """Return recent heartbeat check rows."""
    init_db(db_path)
    with _cursor(db_path) as cur:
        cur.execute(
            """
            SELECT * FROM heartbeat_checks
            ORDER BY checked_at_utc DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _normalize_correction_value(column: str, value: Any) -> Any:
    """Normalize correction values to canonical storage format."""
    if value is None:
        return None

    if column in {"amount", "balance", "fee", "anomaly_score"}:
        return float(value)

    if column == "event_time_utc":
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_NAIROBI_TZ)
        return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat()

    if column == "tags_json":
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return json.dumps(parsed, ensure_ascii=True)
            except json.JSONDecodeError:
                return json.dumps([part.strip() for part in value.split(",") if part.strip()])
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=True)
        return json.dumps([str(value)], ensure_ascii=True)

    return str(value)


_CORRECTION_FIELD_MAP = {
    "timestamp": "event_time_utc",
    "event_time_utc": "event_time_utc",
    "type": "type",
    "amount": "amount",
    "currency": "currency",
    "counterparty_name": "name",
    "name": "name",
    "counterparty_phone": "phone",
    "phone": "phone",
    "account_number": "account_reference",
    "account_reference": "account_reference",
    "balance": "balance",
    "transaction_cost": "fee",
    "fee": "fee",
    "category": "category",
    "tags": "tags_json",
    "tags_json": "tags_json",
    "anomaly_score": "anomaly_score",
}


def apply_transaction_correction(
    transaction_id: str,
    updates: Dict[str, Any],
    reason: str,
    corrected_by: str = "operator",
    db_path: str = _DEFAULT_DB,
) -> dict:
    """Apply controlled transaction corrections and record immutable audit rows."""
    init_db(db_path)
    if not transaction_id:
        raise ValueError("transaction_id is required")
    if not updates:
        raise ValueError("updates cannot be empty")
    if not reason.strip():
        raise ValueError("reason is required")

    with _cursor(db_path) as cur:
        cur.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Transaction not found: {transaction_id}")
        current = dict(row)

        changed: Dict[str, Dict[str, Any]] = {}
        for field, raw_value in updates.items():
            column = _CORRECTION_FIELD_MAP.get(field)
            if not column:
                raise ValueError(f"Unsupported correction field: {field}")
            new_value = _normalize_correction_value(column, raw_value)
            old_value = current.get(column)
            if old_value == new_value:
                continue
            changed[column] = {
                "field": field,
                "column": column,
                "old": old_value,
                "new": new_value,
            }

        if not changed:
            return {
                "status": "no_change",
                "transaction_id": transaction_id,
                "changes": {},
            }

        set_clause = ", ".join(f"{col} = ?" for col in changed.keys())
        params = [entry["new"] for entry in changed.values()]
        params.append(transaction_id)
        cur.execute(
            f"UPDATE transactions SET {set_clause} WHERE transaction_id = ?",
            params,
        )

        corrected_at = _utc_now_iso()
        for entry in changed.values():
            cur.execute(
                """
                INSERT INTO transaction_corrections
                (transaction_id, field_name, old_value, new_value,
                 reason, corrected_by, corrected_at_utc, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    entry["field"],
                    None if entry["old"] is None else str(entry["old"]),
                    None if entry["new"] is None else str(entry["new"]),
                    reason.strip(),
                    corrected_by.strip() or "operator",
                    corrected_at,
                    corrected_at,
                ),
            )

        return {
            "status": "updated",
            "transaction_id": transaction_id,
            "changes": {
                entry["field"]: {"old": entry["old"], "new": entry["new"]}
                for entry in changed.values()
            },
            "reason": reason.strip(),
            "corrected_by": corrected_by.strip() or "operator",
            "corrected_at_utc": corrected_at,
        }


def list_transaction_corrections(
    db_path: str = _DEFAULT_DB,
    transaction_id: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    """List correction audit records."""
    init_db(db_path)
    query = "SELECT * FROM transaction_corrections WHERE 1=1"
    params: list = []

    if transaction_id:
        query += " AND transaction_id = ?"
        params.append(transaction_id)

    query += " ORDER BY corrected_at_utc DESC, id DESC LIMIT ?"
    params.append(limit)

    with _cursor(db_path) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def close_connection(db_path: str = _DEFAULT_DB) -> None:
    """Close and remove cached connection for *db_path*."""
    if hasattr(_local, "connections") and db_path in _local.connections:
        _local.connections[db_path].close()
        del _local.connections[db_path]
