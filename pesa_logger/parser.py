"""Regex-based M-Pesa SMS parsing engine."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


PARSER_VERSION = "v1.0.0"


@dataclass
class Transaction:
    """Represents a parsed M-Pesa transaction."""

    transaction_id: str
    type: str  # send, receive, paybill, till, airtime, withdraw, deposit, reversal
    amount: float
    currency: str = "KES"
    counterparty_name: Optional[str] = None
    counterparty_phone: Optional[str] = None
    account_number: Optional[str] = None
    balance: Optional[float] = None
    transaction_cost: Optional[float] = None
    timestamp: Optional[datetime] = None
    raw_sms: str = ""
    category: Optional[str] = None
    tags: list = field(default_factory=list)
    parser_version: str = PARSER_VERSION
    parse_confidence: float = 0.98

    def to_dict(self) -> dict:
        """Convert transaction to a dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "type": self.type,
            "amount": self.amount,
            "currency": self.currency,
            "counterparty_name": self.counterparty_name,
            "counterparty_phone": self.counterparty_phone,
            "account_number": self.account_number,
            "balance": self.balance,
            "transaction_cost": self.transaction_cost,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "raw_sms": self.raw_sms,
            "category": self.category,
            "tags": self.tags,
            "parser_version": self.parser_version,
            "parse_confidence": self.parse_confidence,
        }


# ─── Amount helpers ──────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(r"Ksh\s*([\d,]+\.?\d*)", re.IGNORECASE)


def _parse_amount(text: str) -> float:
    """Extract a numeric amount from a string like 'Ksh1,500.00'."""
    match = _AMOUNT_RE.search(text)
    if not match:
        raise ValueError(f"No amount found in: {text!r}")
    return float(match.group(1).replace(",", ""))


def _parse_all_amounts(text: str) -> list:
    """Return all amounts found in *text* as floats."""
    return [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(text)]


# ─── Timestamp helper ─────────────────────────────────────────────────────────

_DATE_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM))",
    re.IGNORECASE,
)


def _parse_timestamp(text: str) -> Optional[datetime]:
    """Parse M-Pesa date/time strings like '21/2/26 at 10:30 AM'."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    date_str, time_str = match.group(1), match.group(2).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", f"{fmt} %I:%M %p")
        except ValueError:
            continue
    return None


# ─── Transaction-type patterns ────────────────────────────────────────────────

# Each pattern must expose named groups:  tid, amount  (required)
# Optional groups: name, phone, account, balance, cost

_PATTERNS = {
    "receive": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?You have received Ksh\s*(?P<amount>[\d,]+\.?\d*)"
        r"(?: from (?P<name>[A-Z ]+?) (?P<phone>\d{10,12}))?"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)",
        re.IGNORECASE | re.DOTALL,
    ),
    "send": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?Ksh\s*(?P<amount>[\d,]+\.?\d*) sent to"
        r"(?: (?P<name>[A-Z ]+?) (?P<phone>\d{10,12}))?"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)"
        r"(?:.*?cost,?\s*Ksh\s*(?P<cost>[\d,]+\.?\d*))?",
        re.IGNORECASE | re.DOTALL,
    ),
    "paybill": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?Ksh\s*(?P<amount>[\d,]+\.?\d*) paid to (?P<name>[A-Z0-9 &\-\.]+)"
        r" for account (?P<account>\S+)"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)"
        r"(?:.*?cost,?\s*Ksh\s*(?P<cost>[\d,]+\.?\d*))?",
        re.IGNORECASE | re.DOTALL,
    ),
    # airtime must be checked before the generic till pattern
    "airtime": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?Ksh\s*(?P<amount>[\d,]+\.?\d*) paid to Airtime"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)",
        re.IGNORECASE | re.DOTALL,
    ),
    "till": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?Ksh\s*(?P<amount>[\d,]+\.?\d*) paid to (?P<name>[A-Z0-9 &\-\.]+)"
        r"(?! for account)"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)"
        r"(?:.*?cost,?\s*Ksh\s*(?P<cost>[\d,]+\.?\d*))?",
        re.IGNORECASE | re.DOTALL,
    ),
    "withdraw": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?(?:Withdraw\s*)?Ksh\s*(?P<amount>[\d,]+\.?\d*)\s*(?:withdrawn|from)\b"
        r".*?(?:New\s+M-?PESA\s+)?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)"
        r"(?:.*?cost,?\s*Ksh\s*(?P<cost>[\d,]+\.?\d*))?",
        re.IGNORECASE | re.DOTALL,
    ),
    "deposit": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?Ksh\s*(?P<amount>[\d,]+\.?\d*) deposited"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)",
        re.IGNORECASE | re.DOTALL,
    ),
    "reversal": re.compile(
        r"(?P<tid>[A-Z0-9]+) Confirmed\."
        r".*?reversal of Ksh\s*(?P<amount>[\d,]+\.?\d*)"
        r".*?balance is Ksh\s*(?P<balance>[\d,]+\.?\d*)",
        re.IGNORECASE | re.DOTALL,
    ),
}


def _get(match: re.Match, group: str, default=None):
    """Safely retrieve a named group from a regex match."""
    try:
        val = match.group(group)
        return val if val is not None else default
    except IndexError:
        return default


def _float_group(match: re.Match, group: str) -> Optional[float]:
    val = _get(match, group)
    if val is None:
        return None
    return float(val.replace(",", ""))


def parse_sms(sms_text: str) -> Optional[Transaction]:
    """Parse a raw M-Pesa SMS string and return a :class:`Transaction`.

    Returns ``None`` if the SMS cannot be recognised as an M-Pesa notification.
    """
    text = sms_text.strip()

    for tx_type, pattern in _PATTERNS.items():
        m = pattern.search(text)
        if not m:
            continue

        tid = _get(m, "tid", "UNKNOWN")
        amount = _float_group(m, "amount") or 0.0
        balance = _float_group(m, "balance")
        cost = _float_group(m, "cost")
        name = _get(m, "name")
        phone = _get(m, "phone")
        account = _get(m, "account")

        if name:
            name = name.strip()

        timestamp = _parse_timestamp(text)

        return Transaction(
            transaction_id=tid,
            type=tx_type,
            amount=amount,
            counterparty_name=name,
            counterparty_phone=phone,
            account_number=account,
            balance=balance,
            transaction_cost=cost,
            timestamp=timestamp,
            raw_sms=text,
            parser_version=PARSER_VERSION,
            parse_confidence=0.98,
        )

    return None
