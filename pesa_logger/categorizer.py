"""Transaction categorization engine — rule-based with AI fallback.

Pipeline:
  1. Rule-based keyword match (instant, free)
  2. If result is "Other" or confidence is low → AI categorization
  3. AI results are cached in-process to avoid repeated calls
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional, Tuple

from pesa_logger.parser import Transaction

# ─── Keyword rules ────────────────────────────────────────────────────────────

_KEYWORD_RULES: Dict[str, list[str]] = {
    "Utilities": [
        r"kenya power", r"kplc", r"nairobi water", r"nairobi city water",
        r"water", r"stima", r"electricity", r"sewerage",
    ],
    "Telecommunications": [
        r"safaricom", r"airtel", r"telkom", r"airtime", r"data bundle",
        r"faiba", r"zuku",
    ],
    "Food & Groceries": [
        r"naivas", r"carrefour", r"quickmart", r"cleanshelf", r"grocery",
        r"supermarket", r"food", r"restaurant", r"cafe", r"kfc", r"java",
        r"chicken", r"pizza", r"burger", r"eatery", r"hotel",
    ],
    "Transport": [
        r"uber", r"bolt", r"little cab", r"matatu", r"bus", r"sacco",
        r"transit", r"fare", r"parking", r"fuel", r"petrol", r"shell",
        r"total", r"rubis",
    ],
    "Education": [
        r"school", r"college", r"university", r"fee", r"tuition", r"knec",
        r"kuccps", r"scholarship",
    ],
    "Healthcare": [
        r"hospital", r"clinic", r"pharmacy", r"health", r"medical", r"nhif",
        r"chemist", r"doctor", r"dispensary",
    ],
    "Financial Services": [
        r"equity", r"kcb", r"cooperative", r"absa", r"stanbic", r"dtb",
        r"family bank", r"ncba", r"bank", r"loan", r"fuliza",
        r"mshwari", r"kcb mpesa", r"faulu", r"postbank",
    ],
    "Rent & Housing": [
        r"rent", r"landlord", r"caretaker", r"estate", r"housing",
        r"apartment", r"bedsitter",
    ],
    "Entertainment": [
        r"netflix", r"showmax", r"cinema", r"game", r"dstv", r"gotv",
        r"multichoice", r"spotify", r"youtube",
    ],
    "Insurance": [
        r"insurance", r"jubilee", r"britam", r"cic", r"aar", r"madison",
        r"old mutual", r"kenya orient",
    ],
    "Government": [
        r"kra", r"ntsa", r"county", r"government", r"ecitizen", r"huduma",
        r"nssf", r"nhif", r"nairobi county",
    ],
}

_TYPE_DEFAULTS: Dict[str, str] = {
    "receive": "Income",
    "send": "Personal Transfer",
    "withdraw": "Cash Withdrawal",
    "deposit": "Cash Deposit",
    "airtime": "Telecommunications",
    "reversal": "Reversal",
    "paybill": "Bill Payment",
    "till": "Shopping",
}

# In-process AI category cache: counterparty_key → (category, confidence)
_AI_CATEGORY_CACHE: Dict[str, Tuple[str, float]] = {}


# ─── Rule-based categorization ────────────────────────────────────────────────

def _rule_based_category(tx: Transaction) -> Tuple[str, float]:
    """
    Return (category, confidence) from keyword rules.
    Confidence is 1.0 for keyword match, 0.6 for type-default.
    """
    search_text = " ".join(filter(None, [
        tx.counterparty_name or "",
        tx.account_number or "",
    ])).lower()

    for category, patterns in _KEYWORD_RULES.items():
        for pattern in patterns:
            if pattern and re.search(pattern, search_text, re.IGNORECASE):
                return category, 1.0

    default = _TYPE_DEFAULTS.get(tx.type, "Other")
    confidence = 0.6 if default != "Other" else 0.2
    return default, confidence


# ─── AI fallback categorization ───────────────────────────────────────────────

def _ai_categorize(tx: Transaction) -> Tuple[str, float]:
    """
    Call AIEngine to categorize a transaction.
    Returns (category, confidence). Falls back to "Other" on any failure.
    """
    cache_key = f"{(tx.counterparty_name or '').lower().strip()}|{(tx.account_number or '').lower().strip()}|{tx.type}"

    if cache_key in _AI_CATEGORY_CACHE:
        return _AI_CATEGORY_CACHE[cache_key]

    try:
        from pesa_logger.ai_engine import get_engine
        from pesa_logger.prompts import load as load_prompt

        engine = get_engine()
        system = load_prompt("category_suggest")

        user = (
            f"Transaction type: {tx.type}\n"
            f"Counterparty: {tx.counterparty_name or 'Unknown'}\n"
            f"Account/Reference: {tx.account_number or 'N/A'}\n"
            f"Amount: KES {tx.amount:,.2f}"
        )

        resp = engine.complete_json(user=user, system=system)

        if resp.success:
            try:
                data = json.loads(resp.content)
                category = str(data.get("category", "Other")).strip()
                confidence = float(data.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
                _AI_CATEGORY_CACHE[cache_key] = (category, confidence)
                return category, confidence
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

    except Exception:  # noqa: BLE001
        pass

    _AI_CATEGORY_CACHE[cache_key] = ("Other", 0.1)
    return "Other", 0.1


# ─── Public API ───────────────────────────────────────────────────────────────

def categorize(tx: Transaction, use_ai_fallback: bool = True) -> str:
    """
    Return a category string for *tx*.

    Pipeline:
    1. Keyword rule match (confidence = 1.0)
    2. Type default (confidence = 0.6)
    3. AI fallback if confidence < 0.7 and use_ai_fallback=True
    """
    category, confidence = _rule_based_category(tx)

    if use_ai_fallback and confidence < 0.7:
        ai_category, ai_confidence = _ai_categorize(tx)
        if ai_confidence > confidence:
            return ai_category

    return category


def categorize_with_confidence(
    tx: Transaction,
    use_ai_fallback: bool = True,
) -> Tuple[str, float, str]:
    """
    Return (category, confidence, source) for *tx*.
    source is one of: "keyword", "type_default", "ai", "fallback"
    """
    category, confidence = _rule_based_category(tx)
    source = "keyword" if confidence == 1.0 else "type_default"

    if use_ai_fallback and confidence < 0.7:
        ai_category, ai_confidence = _ai_categorize(tx)
        if ai_confidence > confidence:
            return ai_category, ai_confidence, "ai"

    return category, confidence, source


def categorize_and_apply(tx: Transaction) -> Transaction:
    """Categorize *tx* in-place and return it."""
    tx.category = categorize(tx)
    return tx


def tag_transaction(tx: Transaction) -> Transaction:
    """Attach descriptive tags to *tx* based on amount, type, and category."""
    tags: list[str] = []

    if tx.amount >= 50_000:
        tags.append("very-high-value")
    elif tx.amount >= 10_000:
        tags.append("high-value")
    elif tx.amount <= 50:
        tags.append("micro")

    if tx.type in ("send", "withdraw", "paybill", "till", "airtime"):
        tags.append("debit")
    elif tx.type in ("receive", "deposit"):
        tags.append("credit")

    if tx.transaction_cost and tx.transaction_cost > 0:
        tags.append("has-fee")

    if tx.type == "reversal":
        tags.append("reversal")

    if tx.category in ("Financial Services",) and tx.type == "paybill":
        tags.append("loan-payment")

    tx.tags = tags
    return tx


def clear_ai_cache() -> None:
    """Clear the in-process AI category cache."""
    _AI_CATEGORY_CACHE.clear()