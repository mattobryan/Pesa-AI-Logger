"""Transaction categorization engine.

Assigns a human-readable category to each transaction based on the
transaction type, counterparty name, and account number using a
rule-based keyword matching approach.
"""

from __future__ import annotations

import re
from typing import Optional

from pesa_logger.parser import Transaction


# ─── Keyword rules ────────────────────────────────────────────────────────────
# Maps category name → list of regex patterns applied against
# the counterparty_name and account_number fields (case-insensitive).

_KEYWORD_RULES: dict[str, list[str]] = {
    "Utilities": [
        r"kenya power", r"kplc", r"nairobi water", r"water", r"stima",
        r"electricity",
    ],
    "Telecommunications": [
        r"safaricom", r"airtel", r"telkom", r"airtime", r"data bundle",
    ],
    "Food & Groceries": [
        r"naivas", r"carrefour", r"quickmart", r"cleanshelf", r"grocery",
        r"supermarket", r"food", r"restaurant", r"cafe", r"kfc", r"java",
        r"chicken",
    ],
    "Transport": [
        r"uber", r"bolt", r"little", r"matatu", r"bus", r"sacco", r"transit",
    ],
    "Education": [
        r"school", r"college", r"university", r"fee", r"tuition", r"knec",
        r"kuccps",
    ],
    "Healthcare": [
        r"hospital", r"clinic", r"pharmacy", r"health", r"medical", r"nhif",
        r"chemist",
    ],
    "Financial Services": [
        r"equity", r"kcb", r"cooperative", r"absa", r"stanbic", r"dtb",
        r"family bank", r"ncba", r"bank", r"sacco", r"loan", r"fuliza",
        r"mshwari", r"kcb mpesa",
    ],
    "Rent & Housing": [
        r"rent", r"landlord", r"caretaker", r"estate", r"housing",
    ],
    "Entertainment": [
        r"netflix", r"showmax", r"cinema", r"game", r"dstv", r"gotv",
        r"multichoice",
    ],
    "Insurance": [
        r"insurance", r"jubilee", r"britam", r"cic", r"aar", r"madison",
    ],
    "Government": [
        r"kra", r"ntsa", r"county", r"government", r"ecitizen", r"huduma",
        r"nssf", r"nhif",
    ],
    "Personal Transfer": [
        r"",  # matched by type, not keyword — handled below
    ],
}

# Map transaction types to default categories when no keyword matches
_TYPE_DEFAULTS: dict[str, str] = {
    "receive": "Income",
    "send": "Personal Transfer",
    "withdraw": "Cash Withdrawal",
    "deposit": "Cash Deposit",
    "airtime": "Telecommunications",
    "reversal": "Reversal",
    "paybill": "Bill Payment",
    "till": "Shopping",
}


def categorize(tx: Transaction) -> str:
    """Return a category string for *tx*.

    The rules are evaluated in order:
    1. Keyword match on counterparty_name / account_number.
    2. Transaction-type default.
    """
    search_text = " ".join(
        filter(
            None,
            [
                tx.counterparty_name or "",
                tx.account_number or "",
            ],
        )
    ).lower()

    for category, patterns in _KEYWORD_RULES.items():
        for pattern in patterns:
            if pattern and re.search(pattern, search_text, re.IGNORECASE):
                return category

    return _TYPE_DEFAULTS.get(tx.type, "Other")


def categorize_and_apply(tx: Transaction) -> Transaction:
    """Categorize *tx* in-place and return it."""
    tx.category = categorize(tx)
    return tx


def tag_transaction(tx: Transaction) -> Transaction:
    """Attach descriptive tags to *tx* based on amount and type."""
    tags: list[str] = []

    if tx.amount >= 10_000:
        tags.append("high-value")
    elif tx.amount <= 50:
        tags.append("micro")

    if tx.type in ("send", "withdraw", "paybill", "till", "airtime"):
        tags.append("debit")
    elif tx.type in ("receive", "deposit"):
        tags.append("credit")

    if tx.transaction_cost and tx.transaction_cost > 0:
        tags.append("has-fee")

    tx.tags = tags
    return tx
