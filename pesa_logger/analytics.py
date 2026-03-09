"""Production-grade AI analytics engine for Pesa AI Logger.

Provides deep financial intelligence: statistical analysis, trend detection,
forecasting, behavioural profiling, and AI-generated narrative insights.

All AI calls are routed through AIEngine — provider-agnostic and gracefully
degraded when no AI provider is configured.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pesa_logger.database import list_transactions

DEBIT_TYPES = {"send", "withdraw", "paybill", "till", "airtime"}
CREDIT_TYPES = {"receive", "deposit"}

# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class CategoryBreakdown:
    category: str
    total: float
    count: int
    percentage: float
    avg_per_transaction: float

@dataclass
class CashflowDay:
    date: str
    inflow: float
    outflow: float
    net: float
    transaction_count: int

@dataclass
class CounterpartyProfile:
    name: str
    transaction_count: int
    total_sent: float
    total_received: float
    net: float
    last_seen: Optional[str]
    risk_flags: List[str]

@dataclass
class SpendingForecast:
    period: str
    projected_spend: float
    projected_income: float
    projected_net: float
    confidence: str       # "high" | "medium" | "low"
    basis_days: int

@dataclass
class FinancialHealthScore:
    score: int            # 0-100
    grade: str            # A-F
    savings_rate: float
    income_stability: float
    spend_diversity: float
    unusual_activity_count: int
    summary: str

@dataclass
class InsightReport:
    generated_at: str
    period_days: int
    total_in: float
    total_out: float
    net: float
    transaction_count: int
    top_categories: List[CategoryBreakdown]
    cashflow_trend: List[CashflowDay]
    counterparty_profiles: List[CounterpartyProfile]
    spending_forecast: Optional[SpendingForecast]
    health_score: Optional[FinancialHealthScore]
    ai_narrative: str
    ai_spending_coach: str
    ai_provider: str
    insights: List[str]
    week_over_week: Dict[str, Any]
    time_of_day_breakdown: Dict[str, float]
    day_of_week_breakdown: Dict[str, float]


# ─── Statistical helpers ──────────────────────────────────────────────────────

def _safe_mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0

def _safe_stdev(values: List[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0

def _safe_median(values: List[float]) -> float:
    return statistics.median(values) if values else 0.0

def _linear_trend(values: List[float]) -> float:
    """Return slope of a simple OLS linear regression (positive = growing)."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = _safe_mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0

def _parse_ts(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None


# ─── Core analytics functions ─────────────────────────────────────────────────

def top_spending_categories(
    db_path: str = "pesa_logger.db",
    limit: int = 5,
    days: int = 30,
) -> List[CategoryBreakdown]:
    """Return the top spending categories with full breakdown."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    totals: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)

    total_spend = 0.0
    for tx in transactions:
        if tx.get("type") in DEBIT_TYPES:
            cat = tx.get("category") or "Uncategorized"
            amount = tx.get("amount", 0) or 0
            totals[cat] += amount
            counts[cat] += 1
            total_spend += amount

    result = []
    for cat, total in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]:
        cnt = counts[cat]
        result.append(CategoryBreakdown(
            category=cat,
            total=round(total, 2),
            count=cnt,
            percentage=round((total / total_spend * 100) if total_spend else 0, 1),
            avg_per_transaction=round(total / cnt if cnt else 0, 2),
        ))
    return result


def cashflow_trend(
    db_path: str = "pesa_logger.db",
    days: int = 90,
) -> List[CashflowDay]:
    """Return day-by-day cashflow with inflow, outflow, net, and count."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    by_day: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"in": 0.0, "out": 0.0, "count": 0}
    )

    for tx in transactions:
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        day = dt.strftime("%Y-%m-%d")
        amount = tx.get("amount", 0) or 0
        if tx.get("type") in CREDIT_TYPES:
            by_day[day]["in"] += amount
        elif tx.get("type") in DEBIT_TYPES:
            by_day[day]["out"] += amount
        by_day[day]["count"] += 1

    return [
        CashflowDay(
            date=d,
            inflow=round(v["in"], 2),
            outflow=round(v["out"], 2),
            net=round(v["in"] - v["out"], 2),
            transaction_count=v["count"],
        )
        for d, v in sorted(by_day.items())
    ]


def frequent_counterparties(
    db_path: str = "pesa_logger.db",
    limit: int = 10,
    days: int = 90,
) -> List[CounterpartyProfile]:
    """Return counterparty profiles with net flow and risk flags."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "sent": 0.0, "received": 0.0, "count": 0, "last_seen": None, "amounts": []
    })

    for tx in transactions:
        name = tx.get("counterparty_name") or tx.get("counterparty_phone")
        if not name:
            continue
        amount = tx.get("amount", 0) or 0
        ts = tx.get("timestamp")
        d = data[name]
        d["count"] += 1
        d["amounts"].append(amount)
        if tx.get("type") in DEBIT_TYPES:
            d["sent"] += amount
        elif tx.get("type") in CREDIT_TYPES:
            d["received"] += amount
        if ts and (d["last_seen"] is None or ts > d["last_seen"]):
            d["last_seen"] = ts

    profiles = []
    for name, d in sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]:
        risk_flags: List[str] = []
        amounts = d["amounts"]
        if amounts:
            mean = _safe_mean(amounts)
            stdev = _safe_stdev(amounts)
            if stdev > mean * 2:
                risk_flags.append("high-variance-amounts")
        if d["count"] > 20:
            risk_flags.append("high-frequency")
        if d["sent"] > 50000:
            risk_flags.append("large-total-outflow")

        profiles.append(CounterpartyProfile(
            name=name,
            transaction_count=d["count"],
            total_sent=round(d["sent"], 2),
            total_received=round(d["received"], 2),
            net=round(d["received"] - d["sent"], 2),
            last_seen=d["last_seen"],
            risk_flags=risk_flags,
        ))
    return profiles


def spending_velocity(
    db_path: str = "pesa_logger.db",
    days: int = 30,
) -> Dict[str, Any]:
    """Return daily spend velocity with trend direction."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    by_day: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") not in DEBIT_TYPES:
            continue
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        by_day[dt.strftime("%Y-%m-%d")] += tx.get("amount", 0) or 0

    daily_amounts = [by_day[d] for d in sorted(by_day)]
    trend_slope = _linear_trend(daily_amounts)

    return {
        "average_daily_spend": round(_safe_mean(daily_amounts), 2),
        "median_daily_spend": round(_safe_median(daily_amounts), 2),
        "std_daily_spend": round(_safe_stdev(daily_amounts), 2),
        "peak_day_spend": round(max(daily_amounts, default=0), 2),
        "active_days": len(daily_amounts),
        "total_days": days,
        "trend_slope": round(trend_slope, 2),
        "trend_direction": (
            "increasing" if trend_slope > 10
            else "decreasing" if trend_slope < -10
            else "stable"
        ),
    }


def week_over_week_comparison(
    db_path: str = "pesa_logger.db",
) -> Dict[str, Any]:
    """Compare this week vs last week spend and income."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)

    this_week_tx = list_transactions(db_path=db_path, since=this_week_start)
    last_week_tx = list_transactions(db_path=db_path, since=last_week_start, until=this_week_start)

    def _totals(txs: List[dict]) -> Tuple[float, float]:
        spend = sum(t.get("amount", 0) or 0 for t in txs if t.get("type") in DEBIT_TYPES)
        income = sum(t.get("amount", 0) or 0 for t in txs if t.get("type") in CREDIT_TYPES)
        return round(spend, 2), round(income, 2)

    this_spend, this_income = _totals(this_week_tx)
    last_spend, last_income = _totals(last_week_tx)

    def _pct_change(current: float, previous: float) -> Optional[float]:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    return {
        "this_week": {
            "spend": this_spend,
            "income": this_income,
            "net": round(this_income - this_spend, 2),
        },
        "last_week": {
            "spend": last_spend,
            "income": last_income,
            "net": round(last_income - last_spend, 2),
        },
        "spend_change_pct": _pct_change(this_spend, last_spend),
        "income_change_pct": _pct_change(this_income, last_income),
        "verdict": (
            "spending_up" if this_spend > last_spend * 1.1
            else "spending_down" if this_spend < last_spend * 0.9
            else "spending_stable"
        ),
    }


def time_of_day_analysis(
    db_path: str = "pesa_logger.db",
    days: int = 90,
) -> Dict[str, float]:
    """Return total spend by hour-of-day bucket."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    buckets: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") not in DEBIT_TYPES:
            continue
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        hour = dt.hour
        if 6 <= hour < 12:
            label = "morning (6-12)"
        elif 12 <= hour < 17:
            label = "afternoon (12-17)"
        elif 17 <= hour < 21:
            label = "evening (17-21)"
        elif 21 <= hour or hour < 1:
            label = "night (21-01)"
        else:
            label = "late night (01-06)"
        buckets[label] += tx.get("amount", 0) or 0

    return {k: round(v, 2) for k, v in sorted(buckets.items())}


def day_of_week_analysis(
    db_path: str = "pesa_logger.db",
    days: int = 90,
) -> Dict[str, float]:
    """Return total spend by day of week."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    days_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday",
    }
    buckets: Dict[str, float] = defaultdict(float)

    for tx in transactions:
        if tx.get("type") not in DEBIT_TYPES:
            continue
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        buckets[days_map[dt.weekday()]] += tx.get("amount", 0) or 0

    return {k: round(v, 2) for k, v in buckets.items()}


def spending_forecast(
    db_path: str = "pesa_logger.db",
    horizon_days: int = 30,
) -> SpendingForecast:
    """Project spend and income for the next period using linear regression."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    transactions = list_transactions(db_path=db_path, since=since)

    by_week_spend: Dict[int, float] = defaultdict(float)
    by_week_income: Dict[int, float] = defaultdict(float)

    for tx in transactions:
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        week = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).days // 7
        amount = tx.get("amount", 0) or 0
        if tx.get("type") in DEBIT_TYPES:
            by_week_spend[week] += amount
        elif tx.get("type") in CREDIT_TYPES:
            by_week_income[week] += amount

    spend_series = [by_week_spend.get(w, 0) for w in sorted(by_week_spend)]
    income_series = [by_week_income.get(w, 0) for w in sorted(by_week_income)]

    weeks_in_horizon = horizon_days / 7

    avg_spend = _safe_mean(spend_series) if spend_series else 0
    avg_income = _safe_mean(income_series) if income_series else 0
    trend = _linear_trend(spend_series)

    projected_spend = max(0, (avg_spend + trend) * weeks_in_horizon)
    projected_income = avg_income * weeks_in_horizon

    basis = len(spend_series)
    confidence = "high" if basis >= 10 else "medium" if basis >= 4 else "low"

    return SpendingForecast(
        period=f"next {horizon_days} days",
        projected_spend=round(projected_spend, 2),
        projected_income=round(projected_income, 2),
        projected_net=round(projected_income - projected_spend, 2),
        confidence=confidence,
        basis_days=basis * 7,
    )


def financial_health_score(
    db_path: str = "pesa_logger.db",
    days: int = 30,
) -> FinancialHealthScore:
    """Compute a 0-100 financial health score with letter grade."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    total_in = sum(
        t.get("amount", 0) or 0 for t in transactions if t.get("type") in CREDIT_TYPES
    )
    total_out = sum(
        t.get("amount", 0) or 0 for t in transactions if t.get("type") in DEBIT_TYPES
    )

    # Savings rate component (0–40 points)
    savings_rate = ((total_in - total_out) / total_in) if total_in > 0 else 0
    savings_rate = max(0.0, min(1.0, savings_rate))
    savings_score = savings_rate * 40

    # Spend diversity (0–30 points) — more categories = more controlled spending
    categories = {
        t.get("category") for t in transactions if t.get("type") in DEBIT_TYPES
    }
    diversity = min(len(categories) / 8, 1.0)
    diversity_score = diversity * 30

    # Income stability (0–20 points)
    by_week: Dict[int, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") not in CREDIT_TYPES:
            continue
        dt = _parse_ts(tx.get("timestamp"))
        if dt:
            week = dt.isocalendar()[1]
            by_week[week] += tx.get("amount", 0) or 0

    income_values = list(by_week.values())
    if len(income_values) > 1:
        cv = (
            _safe_stdev(income_values) / _safe_mean(income_values)
            if _safe_mean(income_values)
            else 1
        )
        stability = max(0.0, 1 - cv)
    else:
        stability = 0.5
    stability_score = stability * 20

    # Unusual activity penalty (up to 10 points lost)
    from pesa_logger.anomaly import detect_anomalies
    anomalies = detect_anomalies(db_path=db_path, lookback_days=days)
    unusual_count = len(anomalies)
    anomaly_penalty = min(10, unusual_count * 2)

    raw_score = savings_score + diversity_score + stability_score - anomaly_penalty
    score = max(0, min(100, int(raw_score)))

    grade = (
        "A" if score >= 85
        else "B" if score >= 70
        else "C" if score >= 55
        else "D" if score >= 40
        else "F"
    )

    summary_map = {
        "A": "Excellent financial health. Strong savings and stable income.",
        "B": "Good financial health. Minor areas to watch.",
        "C": "Fair financial health. Review spending patterns.",
        "D": "Poor financial health. Significant action needed.",
        "F": "Critical financial health. Immediate review recommended.",
    }

    return FinancialHealthScore(
        score=score,
        grade=grade,
        savings_rate=round(savings_rate * 100, 1),
        income_stability=round(stability * 100, 1),
        spend_diversity=round(diversity * 100, 1),
        unusual_activity_count=unusual_count,
        summary=summary_map[grade],
    )


# ─── AI narrative generation ──────────────────────────────────────────────────

def _build_insights_context(
    transactions: List[dict],
    top_cats: List[CategoryBreakdown],
    velocity: Dict[str, Any],
    wow: Dict[str, Any],
    total_in: float,
    total_out: float,
    days: int,
) -> str:
    """Build a compact JSON context blob for the AI narrative prompt."""
    return json.dumps({
        "period_days": days,
        "total_income_kes": round(total_in, 2),
        "total_spend_kes": round(total_out, 2),
        "net_kes": round(total_in - total_out, 2),
        "transaction_count": len(transactions),
        "avg_daily_spend_kes": velocity.get("average_daily_spend", 0),
        "spend_trend": velocity.get("trend_direction", "stable"),
        "top_categories": [
            {"name": c.category, "total_kes": c.total, "pct": c.percentage}
            for c in top_cats[:5]
        ],
        "week_over_week": wow,
    }, indent=2)


def generate_ai_narrative(context_json: str) -> Tuple[str, str]:
    """
    Generate AI narrative and spending coach messages from a context JSON blob.

    Parameters
    ----------
    context_json : JSON string produced by _build_insights_context().

    Returns
    -------
    (narrative, coach_message) — both strings.
    Returns human-readable fallback strings when AI_PROVIDER=stub or unavailable.
    """
    from pesa_logger.ai_engine import get_engine
    from pesa_logger.prompts import load as load_prompt

    engine = get_engine()

    insights_system = load_prompt("insights")
    coach_system = load_prompt("spending_coach")

    narrative_resp = engine.complete(
        system=insights_system,
        user=f"Here is the financial summary data:\n\n{context_json}",
    )
    coach_resp = engine.complete(
        system=coach_system,
        user=f"Monthly spending breakdown:\n\n{context_json}",
    )

    narrative = narrative_resp.content if narrative_resp.success else (
        "AI narrative unavailable — configure AI_PROVIDER in your .env to enable."
    )
    coach = coach_resp.content if coach_resp.success else (
        "Spending coach unavailable — configure AI_PROVIDER in your .env to enable."
    )

    return narrative, coach


def generate_insights(
    db_path: str = "pesa_logger.db",
    days: int = 30,
) -> List[str]:
    """
    Generate plain-English financial insights.

    Backward-compatible with the original signature — returns List[str].
    """
    report = generate_full_report(db_path=db_path, days=days)
    insights = list(report.insights)
    if report.ai_narrative and "unavailable" not in report.ai_narrative:
        insights.append(report.ai_narrative)
    return insights


def generate_full_report(
    db_path: str = "pesa_logger.db",
    days: int = 30,
    include_forecast: bool = True,
    include_health_score: bool = True,
) -> InsightReport:
    """
    Generate a comprehensive InsightReport — the main analytics entry point.

    Runs all analytics in sequence and returns a single structured object
    ready for JSON serialisation via report_to_dict().
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    transactions = list_transactions(db_path=db_path, since=since)

    total_in = sum(
        t.get("amount", 0) or 0 for t in transactions if t.get("type") in CREDIT_TYPES
    )
    total_out = sum(
        t.get("amount", 0) or 0 for t in transactions if t.get("type") in DEBIT_TYPES
    )
    net = total_in - total_out

    top_cats = top_spending_categories(db_path=db_path, limit=8, days=days)
    trend = cashflow_trend(db_path=db_path, days=days)
    counterparties = frequent_counterparties(db_path=db_path, limit=10, days=days)
    velocity = spending_velocity(db_path=db_path, days=days)
    wow = week_over_week_comparison(db_path=db_path)
    tod = time_of_day_analysis(db_path=db_path, days=days)
    dow = day_of_week_analysis(db_path=db_path, days=days)

    forecast = spending_forecast(db_path=db_path) if include_forecast else None
    health = financial_health_score(db_path=db_path, days=days) if include_health_score else None

    # ── Rule-based insights (always available, no AI needed) ──────────────────
    insights: List[str] = []

    if top_cats:
        top = top_cats[0]
        insights.append(
            f"Top spending category: {top.category} at KES {top.total:,.2f} "
            f"({top.percentage}% of total spend)."
        )

    avg = velocity["average_daily_spend"]
    if avg > 0:
        direction = velocity["trend_direction"]
        insights.append(f"Daily spend averaging KES {avg:,.2f} — trend is {direction}.")

    if net >= 0:
        insights.append(f"Net cashflow: +KES {net:,.2f} surplus over {days} days.")
    else:
        insights.append(
            f"Net cashflow: -KES {abs(net):,.2f} deficit over {days} days. "
            "Consider reducing discretionary spend."
        )

    wow_pct = wow.get("spend_change_pct")
    if wow_pct is not None and abs(wow_pct) > 5:
        direction_word = "up" if wow_pct > 0 else "down"
        insights.append(f"Week-over-week spending is {direction_word} {abs(wow_pct)}%.")

    if tod:
        peak_period = max(tod, key=tod.get)
        insights.append(
            f"Most spending happens in the {peak_period} — KES {tod[peak_period]:,.2f}."
        )

    if health:
        insights.append(
            f"Financial health score: {health.score}/100 (Grade {health.grade}). {health.summary}"
        )

    if forecast and forecast.confidence in ("high", "medium"):
        net_word = "surplus" if forecast.projected_net >= 0 else "deficit"
        insights.append(
            f"Forecast ({forecast.confidence} confidence): projected KES "
            f"{forecast.projected_spend:,.2f} spend in the next 30 days — "
            f"{net_word} of KES {abs(forecast.projected_net):,.2f}."
        )

    # ── AI narrative ──────────────────────────────────────────────────────────
    context_json = _build_insights_context(
        transactions, top_cats, velocity, wow, total_in, total_out, days
    )
    ai_narrative, ai_coach = generate_ai_narrative(context_json)

    from pesa_logger.ai_engine import get_engine
    ai_provider = get_engine().provider_name

    return InsightReport(
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        period_days=days,
        total_in=round(total_in, 2),
        total_out=round(total_out, 2),
        net=round(net, 2),
        transaction_count=len(transactions),
        top_categories=top_cats,
        cashflow_trend=trend,
        counterparty_profiles=counterparties,
        spending_forecast=forecast,
        health_score=health,
        ai_narrative=ai_narrative,
        ai_spending_coach=ai_coach,
        ai_provider=ai_provider,
        insights=insights,
        week_over_week=wow,
        time_of_day_breakdown=tod,
        day_of_week_breakdown=dow,
    )


def report_to_dict(report: InsightReport) -> Dict[str, Any]:
    """Serialize an InsightReport to a JSON-safe dict."""
    return asdict(report)