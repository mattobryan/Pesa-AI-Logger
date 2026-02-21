"""Financial summaries and CSV/Excel export."""

from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pesa_logger.database import list_transactions


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _group_by_period(transactions: list, period: str) -> Dict[str, list]:
    """Group transactions by 'weekly' or 'monthly' period key."""
    groups: Dict[str, list] = defaultdict(list)
    for tx in transactions:
        dt = _parse_ts(tx.get("timestamp"))
        if not dt:
            continue
        if period == "weekly":
            # ISO week: e.g. "2026-W07"
            key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        else:
            key = dt.strftime("%Y-%m")
        groups[key].append(tx)
    return dict(groups)


def _summarise_group(transactions: list) -> dict:
    """Compute aggregate stats for a list of transactions."""
    debit_types = {"send", "withdraw", "paybill", "till", "airtime"}
    credit_types = {"receive", "deposit"}

    total_in = sum(t["amount"] for t in transactions if t.get("type") in credit_types)
    total_out = sum(t["amount"] for t in transactions if t.get("type") in debit_types)
    total_fees = sum(
        t.get("transaction_cost") or 0 for t in transactions if t.get("transaction_cost")
    )

    by_category: Dict[str, float] = defaultdict(float)
    for t in transactions:
        cat = t.get("category") or "Uncategorized"
        if t.get("type") in debit_types:
            by_category[cat] += t["amount"]

    amounts = [t["amount"] for t in transactions]
    avg_tx = statistics.mean(amounts) if amounts else 0.0

    return {
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "total_fees": total_fees,
        "transaction_count": len(transactions),
        "average_transaction": avg_tx,
        "spending_by_category": dict(by_category),
    }


# ─── Public API ───────────────────────────────────────────────────────────────

def weekly_summary(
    db_path: str = "pesa_logger.db",
    weeks: int = 4,
) -> Dict[str, dict]:
    """Return weekly financial summaries for the last *weeks* weeks."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=weeks)
    transactions = list_transactions(db_path=db_path, since=since)
    groups = _group_by_period(transactions, "weekly")
    return {k: _summarise_group(v) for k, v in sorted(groups.items())}


def monthly_summary(
    db_path: str = "pesa_logger.db",
    months: int = 6,
) -> Dict[str, dict]:
    """Return monthly financial summaries for the last *months* months."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=months * 30)
    transactions = list_transactions(db_path=db_path, since=since)
    groups = _group_by_period(transactions, "monthly")
    return {k: _summarise_group(v) for k, v in sorted(groups.items())}


def export_csv(
    db_path: str = "pesa_logger.db",
    output_path: Optional[str] = None,
    tx_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> str:
    """Export transactions to CSV.

    If *output_path* is given the file is written there; otherwise the CSV
    content is returned as a string.
    """
    transactions = list_transactions(
        db_path=db_path, tx_type=tx_type, since=since, until=until
    )

    fieldnames = [
        "transaction_id", "type", "amount", "currency",
        "counterparty_name", "counterparty_phone", "account_number",
        "balance", "transaction_cost", "timestamp", "category", "tags",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(transactions)
    content = buf.getvalue()

    if output_path:
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            fh.write(content)

    return content


def export_excel(
    db_path: str = "pesa_logger.db",
    output_path: str = "transactions.xlsx",
    tx_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> str:
    """Export transactions to an Excel workbook and return the file path."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "openpyxl is required for Excel export. "
            "Install it with: pip install openpyxl"
        ) from exc

    transactions = list_transactions(
        db_path=db_path, tx_type=tx_type, since=since, until=until
    )

    headers = [
        "Transaction ID", "Type", "Amount (KES)", "Counterparty",
        "Phone", "Account", "Balance", "Fee", "Timestamp", "Category", "Tags",
    ]
    field_map = [
        "transaction_id", "type", "amount", "counterparty_name",
        "counterparty_phone", "account_number", "balance",
        "transaction_cost", "timestamp", "category", "tags",
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F6B2E")  # Safaricom green

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill

    for row_idx, tx in enumerate(transactions, start=2):
        for col_idx, field in enumerate(field_map, start=1):
            ws.cell(row=row_idx, column=col_idx, value=tx.get(field))

    wb.save(output_path)
    return output_path
