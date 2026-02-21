"""Anomaly detection for unusual financial activity.

Detects anomalies using statistical thresholds computed from the
transaction history stored in the database.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pesa_logger.database import list_transactions


@dataclass
class Anomaly:
    """Describes a detected anomaly."""

    transaction_id: str
    reason: str
    severity: str  # "low", "medium", "high"
    amount: float
    timestamp: Optional[str]

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "reason": self.reason,
            "severity": self.severity,
            "amount": self.amount,
            "timestamp": self.timestamp,
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _amounts_for_type(transactions: list, tx_type: str) -> list:
    return [
        t["amount"] for t in transactions if t.get("type") == tx_type and t.get("amount")
    ]


def _stdev_threshold(values: list, multiplier: float = 2.5) -> float:
    """Return mean + multiplier * stdev as an outlier threshold."""
    if len(values) < 2:
        return float("inf")
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    return mean + multiplier * stdev


# ─── Detection rules ──────────────────────────────────────────────────────────

def detect_large_transaction(
    tx: dict,
    all_transactions: list,
    multiplier: float = 2.5,
) -> Optional[Anomaly]:
    """Flag transactions that are significantly larger than the historical mean."""
    amounts = _amounts_for_type(all_transactions, tx.get("type", ""))
    threshold = _stdev_threshold(amounts, multiplier)
    amount = tx.get("amount", 0)
    if amount > threshold:
        severity = "high" if amount > threshold * 1.5 else "medium"
        return Anomaly(
            transaction_id=tx["transaction_id"],
            reason=f"Amount {amount:,.2f} exceeds statistical threshold {threshold:,.2f}",
            severity=severity,
            amount=amount,
            timestamp=tx.get("timestamp"),
        )
    return None


def detect_rapid_successive(
    transactions: list,
    window_minutes: int = 10,
    threshold_count: int = 3,
) -> List[Anomaly]:
    """Flag bursts of transactions within a short time window."""
    anomalies: List[Anomaly] = []
    timed = [
        t for t in transactions
        if t.get("timestamp") and t.get("type") in ("send", "withdraw", "paybill", "till")
    ]
    timed.sort(key=lambda t: t["timestamp"])

    for i, tx in enumerate(timed):
        try:
            base = datetime.fromisoformat(tx["timestamp"])
        except (ValueError, TypeError):
            continue
        window = [
            t for t in timed[i:]
            if abs(
                (datetime.fromisoformat(t["timestamp"]) - base).total_seconds()
            ) <= window_minutes * 60
        ]
        if len(window) >= threshold_count:
            anomalies.append(
                Anomaly(
                    transaction_id=tx["transaction_id"],
                    reason=(
                        f"{len(window)} debit transactions within {window_minutes} minutes"
                    ),
                    severity="medium",
                    amount=tx.get("amount", 0),
                    timestamp=tx.get("timestamp"),
                )
            )
            break  # report once per burst

    return anomalies


def detect_unusual_hour(tx: dict) -> Optional[Anomaly]:
    """Flag transactions that occur between midnight and 4 AM."""
    ts = tx.get("timestamp")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if 0 <= dt.hour < 4:
        return Anomaly(
            transaction_id=tx["transaction_id"],
            reason=f"Transaction at unusual hour: {dt.strftime('%H:%M')}",
            severity="low",
            amount=tx.get("amount", 0),
            timestamp=ts,
        )
    return None


# ─── Public API ───────────────────────────────────────────────────────────────

def detect_anomalies(
    db_path: str = "pesa_logger.db",
    lookback_days: int = 90,
) -> List[Anomaly]:
    """Run all anomaly detectors against recent transactions.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.
    lookback_days:
        How many days of history to load for baseline calculations.
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback_days)
    all_tx = list_transactions(db_path=db_path, since=since)

    anomalies: List[Anomaly] = []

    for tx in all_tx:
        large = detect_large_transaction(tx, all_tx)
        if large:
            anomalies.append(large)

        unusual = detect_unusual_hour(tx)
        if unusual:
            anomalies.append(unusual)

    rapid = detect_rapid_successive(all_tx)
    anomalies.extend(rapid)

    # Deduplicate by transaction_id + reason
    seen: set = set()
    unique: List[Anomaly] = []
    for a in anomalies:
        key = (a.transaction_id, a.reason)
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique
