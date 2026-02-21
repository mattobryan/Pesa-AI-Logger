"""AI analytics layer — financial insights and behaviour summaries.

Provides rule-based and statistical insights over stored transactions.
An optional OpenAI integration is activated only when the
``OPENAI_API_KEY`` environment variable is set.
"""

from __future__ import annotations

import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pesa_logger.database import list_transactions


# ─── Core insights ────────────────────────────────────────────────────────────

def top_spending_categories(
    db_path: str = "pesa_logger.db",
    limit: int = 5,
    days: int = 30,
) -> List[dict]:
    """Return the top *limit* spending categories over the last *days* days."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    debit_types = {"send", "withdraw", "paybill", "till", "airtime"}
    transactions = list_transactions(db_path=db_path, since=since)

    totals: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") in debit_types:
            cat = tx.get("category") or "Uncategorized"
            totals[cat] += tx.get("amount", 0)

    sorted_cats = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [
        {"category": cat, "total": total} for cat, total in sorted_cats[:limit]
    ]


def cashflow_trend(
    db_path: str = "pesa_logger.db",
    days: int = 90,
) -> Dict[str, dict]:
    """Return a day-by-day cashflow (credits vs debits) for the last *days* days."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    debit_types = {"send", "withdraw", "paybill", "till", "airtime"}
    credit_types = {"receive", "deposit"}

    by_day: Dict[str, dict] = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    for tx in transactions:
        ts = tx.get("timestamp")
        if not ts:
            continue
        try:
            day = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        if tx.get("type") in credit_types:
            by_day[day]["in"] += tx.get("amount", 0)
        elif tx.get("type") in debit_types:
            by_day[day]["out"] += tx.get("amount", 0)

    return dict(sorted(by_day.items()))


def frequent_counterparties(
    db_path: str = "pesa_logger.db",
    limit: int = 10,
    days: int = 90,
) -> List[dict]:
    """Return the most frequently transacted counterparties."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    counter: Counter = Counter()
    totals: Dict[str, float] = defaultdict(float)

    for tx in transactions:
        name = tx.get("counterparty_name") or tx.get("counterparty_phone")
        if not name:
            continue
        counter[name] += 1
        totals[name] += tx.get("amount", 0)

    return [
        {"counterparty": name, "count": count, "total": totals[name]}
        for name, count in counter.most_common(limit)
    ]


def spending_velocity(
    db_path: str = "pesa_logger.db",
    days: int = 30,
) -> dict:
    """Return daily average spend and a simple velocity trend."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    debit_types = {"send", "withdraw", "paybill", "till", "airtime"}
    transactions = list_transactions(db_path=db_path, since=since)

    by_day: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") not in debit_types:
            continue
        ts = tx.get("timestamp")
        if not ts:
            continue
        try:
            day = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        by_day[day] += tx.get("amount", 0)

    daily_amounts = list(by_day.values())
    avg = statistics.mean(daily_amounts) if daily_amounts else 0.0
    std = statistics.stdev(daily_amounts) if len(daily_amounts) > 1 else 0.0

    return {
        "average_daily_spend": avg,
        "std_daily_spend": std,
        "active_days": len(daily_amounts),
        "total_days": days,
    }


def generate_insights(
    db_path: str = "pesa_logger.db",
    days: int = 30,
) -> List[str]:
    """Generate plain-English financial insights from stored transactions.

    Returns a list of insight strings. When the ``OPENAI_API_KEY`` environment
    variable is set, an additional LLM-generated narrative is appended.
    """
    insights: List[str] = []

    top_cats = top_spending_categories(db_path=db_path, limit=3, days=days)
    if top_cats:
        top = top_cats[0]
        insights.append(
            f"Your highest spending category in the last {days} days is "
            f"'{top['category']}' at KES {top['total']:,.2f}."
        )

    velocity = spending_velocity(db_path=db_path, days=days)
    avg = velocity["average_daily_spend"]
    if avg > 0:
        insights.append(
            f"You spend an average of KES {avg:,.2f} per active day."
        )

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)
    credit_types = {"receive", "deposit"}
    debit_types = {"send", "withdraw", "paybill", "till", "airtime"}
    total_in = sum(t["amount"] for t in transactions if t.get("type") in credit_types)
    total_out = sum(t["amount"] for t in transactions if t.get("type") in debit_types)
    net = total_in - total_out
    if net >= 0:
        insights.append(
            f"Net cashflow over the last {days} days: +KES {net:,.2f} (surplus)."
        )
    else:
        insights.append(
            f"Net cashflow over the last {days} days: -KES {abs(net):,.2f} (deficit)."
        )

    # Optional: LLM narrative
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key and insights:
        llm_narrative = _llm_narrative(insights, api_key)
        if llm_narrative:
            insights.append(llm_narrative)

    return insights


def _llm_narrative(insights: List[str], api_key: str) -> Optional[str]:
    """Call the OpenAI API to generate a narrative summary of *insights*."""
    try:
        import openai  # optional dependency

        client = openai.OpenAI(api_key=api_key)
        prompt = (
            "You are a personal financial advisor. Summarise these M-Pesa "
            "transaction insights in 2-3 sentences with actionable advice:\n\n"
            + "\n".join(f"- {i}" for i in insights)
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception:  # noqa: BLE001
        return None
