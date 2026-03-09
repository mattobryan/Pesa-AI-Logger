"""Production-grade anomaly detection with AI explanations.

Detection rules:
  1. Statistical outlier (z-score / stdev threshold)
  2. Rapid successive transactions (burst detection)
  3. Unusual hour (late night activity)
  4. Round number bias (common in fraud)
  5. Duplicate-amount fingerprint (same amount to same party within 24h)
  6. Velocity spike (daily spend > 3x rolling average)
  7. Category spend spike (category suddenly 2x historical norm)

Each anomaly can be enriched with an AI-generated explanation.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pesa_logger.database import list_transactions

DEBIT_TYPES = {"send", "withdraw", "paybill", "till", "airtime"}


# ─── Anomaly dataclass ────────────────────────────────────────────────────────

@dataclass
class Anomaly:
    transaction_id: str
    reason: str
    severity: str           # "low" | "medium" | "high" | "critical"
    amount: float
    timestamp: Optional[str]
    rule: str               # which detector fired
    context: Dict[str, Any] = field(default_factory=dict)
    ai_explanation: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "reason": self.reason,
            "severity": self.severity,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "rule": self.rule,
            "context": self.context,
            "ai_explanation": self.ai_explanation,
        }


# ─── Statistical helpers ──────────────────────────────────────────────────────

def _amounts_for_type(transactions: list, tx_type: str) -> List[float]:
    return [t["amount"] for t in transactions if t.get("type") == tx_type and t.get("amount")]


def _zscore_threshold(values: List[float], multiplier: float = 2.5) -> Tuple[float, float, float]:
    """Return (threshold, mean, stdev)."""
    if len(values) < 2:
        return float("inf"), 0.0, 0.0
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    return mean + multiplier * stdev, mean, stdev


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None


# ─── Detection rules ──────────────────────────────────────────────────────────

def detect_large_transaction(
    tx: dict,
    all_transactions: list,
    multiplier: float = 2.5,
) -> Optional[Anomaly]:
    """Flag transactions significantly larger than historical mean for their type."""
    amounts = _amounts_for_type(all_transactions, tx.get("type", ""))
    threshold, mean, stdev = _zscore_threshold(amounts, multiplier)
    amount = tx.get("amount", 0) or 0

    if amount <= threshold or len(amounts) < 5:
        return None

    zscore = (amount - mean) / stdev if stdev else 0
    severity = "critical" if zscore > 5 else "high" if zscore > 3.5 else "medium"

    return Anomaly(
        transaction_id=tx.get("transaction_id", ""),
        reason=f"Amount KES {amount:,.2f} is {zscore:.1f}σ above the mean (KES {mean:,.2f})",
        severity=severity,
        amount=amount,
        timestamp=tx.get("timestamp"),
        rule="large_transaction",
        context={
            "mean": round(mean, 2),
            "stdev": round(stdev, 2),
            "zscore": round(zscore, 2),
            "threshold": round(threshold, 2),
        },
    )


def detect_rapid_successive(
    transactions: list,
    window_minutes: int = 10,
    threshold_count: int = 3,
) -> List[Anomaly]:
    """Flag bursts of debit transactions within a short time window."""
    anomalies: List[Anomaly] = []
    timed = [
        t for t in transactions
        if t.get("timestamp") and t.get("type") in DEBIT_TYPES
        and t.get("transaction_id")
    ]
    timed.sort(key=lambda t: t["timestamp"])

    reported_bursts: set = set()

    for i, tx in enumerate(timed):
        base_dt = _parse_ts(tx["timestamp"])
        if not base_dt:
            continue

        # FIX: safely parse each timestamp before subtracting
        window = []
        for t in timed[i:]:
            t_dt = _parse_ts(t["timestamp"])
            if t_dt and abs((t_dt - base_dt).total_seconds()) <= window_minutes * 60:
                window.append(t)

        if len(window) >= threshold_count:
            burst_key = frozenset(t.get("transaction_id", "") for t in window)
            if burst_key in reported_bursts:
                continue
            reported_bursts.add(burst_key)

            total_burst = sum(t.get("amount", 0) or 0 for t in window)
            anomalies.append(Anomaly(
                transaction_id=tx.get("transaction_id", ""),
                reason=(
                    f"{len(window)} debit transactions within {window_minutes} minutes "
                    f"(KES {total_burst:,.2f} total)"
                ),
                severity="high",
                amount=tx.get("amount", 0) or 0,
                timestamp=tx.get("timestamp"),
                rule="rapid_successive",
                context={
                    "burst_count": len(window),
                    "window_minutes": window_minutes,
                    "total_amount": round(total_burst, 2),
                    "transaction_ids": [t.get("transaction_id") for t in window],
                },
            ))
    return anomalies


def detect_unusual_hour(tx: dict) -> Optional[Anomaly]:
    """Flag transactions between 01:00 and 05:00 — statistically low-activity period."""
    dt = _parse_ts(tx.get("timestamp"))
    if not dt:
        return None

    if 1 <= dt.hour < 5:
        return Anomaly(
            transaction_id=tx.get("transaction_id", ""),
            reason=f"Transaction at {dt.strftime('%H:%M')} — unusual hour (01:00–05:00)",
            severity="low",
            amount=tx.get("amount", 0) or 0,
            timestamp=tx.get("timestamp"),
            rule="unusual_hour",
            context={"hour": dt.hour, "minute": dt.minute},
        )
    return None


def detect_round_number(tx: dict, all_transactions: list) -> Optional[Anomaly]:
    """
    Flag suspiciously round amounts (>= KES 5,000 divisible by 1,000).
    Only fires when round numbers are unusual for this user.
    """
    amount = tx.get("amount", 0) or 0
    if amount < 5000:
        return None
    if amount % 1000 != 0:
        return None

    total = len(all_transactions)
    if total == 0:
        return None

    round_count = sum(
        1 for t in all_transactions if (t.get("amount", 0) or 0) % 1000 == 0
    )
    round_rate = round_count / total

    if round_rate > 0.4:
        return None  # Round numbers are normal for this user

    return Anomaly(
        transaction_id=tx.get("transaction_id", ""),
        reason=(
            f"Round-number amount KES {amount:,.0f} — "
            f"only {round_rate:.0%} of transactions use round numbers"
        ),
        severity="low",
        amount=amount,
        timestamp=tx.get("timestamp"),
        rule="round_number",
        context={"amount": amount, "round_rate": round(round_rate, 3)},
    )


def detect_duplicate_fingerprint(
    tx: dict,
    all_transactions: list,
    window_hours: int = 24,
) -> Optional[Anomaly]:
    """Flag same-amount, same-counterparty transactions within 24 hours."""
    tx_amount = tx.get("amount", 0) or 0
    tx_name = (tx.get("counterparty_name") or "").strip().lower()
    tx_ts = _parse_ts(tx.get("timestamp"))
    tx_id = tx.get("transaction_id", "")

    if not tx_name or not tx_ts or tx.get("type") not in DEBIT_TYPES:
        return None

    duplicates = []
    for other in all_transactions:
        if other.get("transaction_id") == tx_id:
            continue
        other_amount = other.get("amount", 0) or 0
        other_name = (other.get("counterparty_name") or "").strip().lower()
        other_ts = _parse_ts(other.get("timestamp"))

        if not other_ts or other_name != tx_name:
            continue
        if abs(other_amount - tx_amount) > 0.01:
            continue
        if abs((other_ts - tx_ts).total_seconds()) <= window_hours * 3600:
            duplicates.append(other.get("transaction_id"))

    if duplicates:
        return Anomaly(
            transaction_id=tx_id,
            reason=(
                f"Duplicate: KES {tx_amount:,.2f} to {tx_name} appears "
                f"{len(duplicates) + 1}x within {window_hours}h"
            ),
            severity="high",
            amount=tx_amount,
            timestamp=tx.get("timestamp"),
            rule="duplicate_fingerprint",
            context={
                "counterparty": tx_name,
                "duplicate_ids": duplicates,
                "window_hours": window_hours,
            },
        )
    return None


def detect_velocity_spike(
    tx: dict,
    all_transactions: list,
    spike_multiplier: float = 3.0,
) -> Optional[Anomaly]:
    """Flag a day where total spend is >3x the rolling 30-day daily average."""
    tx_ts = _parse_ts(tx.get("timestamp"))
    if not tx_ts or tx.get("type") not in DEBIT_TYPES:
        return None

    tx_day = tx_ts.strftime("%Y-%m-%d")

    daily_totals: Dict[str, float] = defaultdict(float)
    for t in all_transactions:
        if t.get("type") not in DEBIT_TYPES:
            continue
        dt = _parse_ts(t.get("timestamp"))
        if dt:
            daily_totals[dt.strftime("%Y-%m-%d")] += t.get("amount", 0) or 0

    tx_day_total = daily_totals.get(tx_day, 0)
    historical = [v for d, v in daily_totals.items() if d != tx_day]

    if len(historical) < 7:
        return None

    avg = statistics.mean(historical)
    if avg <= 0:
        return None

    ratio = tx_day_total / avg
    if ratio >= spike_multiplier:
        return Anomaly(
            transaction_id=tx.get("transaction_id", ""),
            reason=(
                f"Daily spend on {tx_day} (KES {tx_day_total:,.2f}) "
                f"is {ratio:.1f}x the rolling average (KES {avg:,.2f})"
            ),
            severity="high" if ratio >= 5 else "medium",
            amount=tx.get("amount", 0) or 0,
            timestamp=tx.get("timestamp"),
            rule="velocity_spike",
            context={
                "day": tx_day,
                "day_total": round(tx_day_total, 2),
                "rolling_avg": round(avg, 2),
                "ratio": round(ratio, 2),
            },
        )
    return None


def detect_category_spike(
    tx: dict,
    all_transactions: list,
    lookback_days: int = 30,
    spike_multiplier: float = 2.0,
) -> Optional[Anomaly]:
    """
    Flag a transaction whose category has suddenly spiked vs its historical norm.

    Compares spend in that category over the last 7 days against the prior
    lookback_days average. Fires when the 7-day total is >= spike_multiplier
    times the historical weekly average for that category.
    """
    if tx.get("type") not in DEBIT_TYPES:
        return None

    category = tx.get("category")
    if not category or category in ("Uncategorized", "Other"):
        return None

    tx_ts = _parse_ts(tx.get("timestamp"))
    if not tx_ts:
        return None

    # Split transactions into recent 7 days vs prior history
    recent_cutoff = tx_ts - timedelta(days=7)
    history_cutoff = tx_ts - timedelta(days=lookback_days)

    recent_cat_total = 0.0
    history_by_week: Dict[int, float] = defaultdict(float)

    for t in all_transactions:
        if t.get("type") not in DEBIT_TYPES:
            continue
        if t.get("category") != category:
            continue
        t_ts = _parse_ts(t.get("timestamp"))
        if not t_ts:
            continue
        amount = t.get("amount", 0) or 0

        if t_ts >= recent_cutoff:
            recent_cat_total += amount
        elif t_ts >= history_cutoff:
            week_num = (t_ts - history_cutoff).days // 7
            history_by_week[week_num] += amount

    if not history_by_week:
        return None  # No historical baseline for this category

    weekly_avg = statistics.mean(list(history_by_week.values()))
    if weekly_avg <= 0:
        return None

    ratio = recent_cat_total / weekly_avg
    if ratio < spike_multiplier:
        return None

    return Anomaly(
        transaction_id=tx.get("transaction_id", ""),
        reason=(
            f"{category} spend this week (KES {recent_cat_total:,.2f}) "
            f"is {ratio:.1f}x the weekly average (KES {weekly_avg:,.2f})"
        ),
        severity="high" if ratio >= 4 else "medium",
        amount=tx.get("amount", 0) or 0,
        timestamp=tx.get("timestamp"),
        rule="category_spike",
        context={
            "category": category,
            "recent_7day_total": round(recent_cat_total, 2),
            "historical_weekly_avg": round(weekly_avg, 2),
            "ratio": round(ratio, 2),
        },
    )


# ─── AI explanation enrichment ────────────────────────────────────────────────

def _enrich_with_ai_explanation(anomaly: Anomaly) -> Anomaly:
    """Add an AI-generated one-sentence explanation to a high/critical anomaly."""
    if anomaly.severity not in ("high", "critical"):
        return anomaly

    try:
        from pesa_logger.ai_engine import get_engine
        from pesa_logger.prompts import load as load_prompt

        engine = get_engine()
        if engine.provider_name == "stub":
            return anomaly

        system = load_prompt("anomaly_explain")
        user = (
            f"Flagged transaction:\n"
            f"- Amount: KES {anomaly.amount:,.2f}\n"
            f"- Rule triggered: {anomaly.rule}\n"
            f"- Reason: {anomaly.reason}\n"
            f"- Context: {anomaly.context}\n"
        )

        resp = engine.complete(system=system, user=user, use_cache=True)
        if resp.success:
            anomaly.ai_explanation = resp.content

    except Exception:  # noqa: BLE001
        pass

    return anomaly


# ─── Public API ───────────────────────────────────────────────────────────────

def detect_anomalies(
    db_path: str = "pesa_logger.db",
    lookback_days: int = 90,
    enrich_with_ai: bool = True,
) -> List[Anomaly]:
    """
    Run all anomaly detectors against recent transactions.

    Parameters
    ----------
    db_path        : SQLite database path.
    lookback_days  : Days of history to load.
    enrich_with_ai : Attach AI explanations to high/critical anomalies.
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback_days)
    all_tx = list_transactions(db_path=db_path, since=since)

    anomalies: List[Anomaly] = []

    # Per-transaction rules
    for tx in all_tx:
        if not tx.get("transaction_id"):
            continue

        for detector in (
            lambda t: detect_large_transaction(t, all_tx),
            detect_unusual_hour,
            lambda t: detect_round_number(t, all_tx),
            lambda t: detect_duplicate_fingerprint(t, all_tx),
            lambda t: detect_velocity_spike(t, all_tx),
            lambda t: detect_category_spike(t, all_tx),
        ):
            result = detector(tx)
            if result:
                anomalies.append(result)

    # Batch rules
    anomalies.extend(detect_rapid_successive(all_tx))

    # Deduplicate by (transaction_id, rule)
    seen: set = set()
    unique: List[Anomaly] = []
    for a in anomalies:
        key = (a.transaction_id, a.rule)
        if key not in seen:
            seen.add(key)
            unique.append(a)

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique.sort(key=lambda a: severity_order.get(a.severity, 9))

    # AI enrichment — cap at 5 calls per run
    if enrich_with_ai:
        for anomaly in [a for a in unique if a.severity in ("high", "critical")][:5]:
            _enrich_with_ai_explanation(anomaly)

    return unique