"""Tests for the transaction categorization engine."""

import pytest

from pesa_logger.categorizer import categorize, categorize_and_apply, tag_transaction
from pesa_logger.parser import Transaction


def _tx(tx_type="send", name=None, account=None, amount=500.0, cost=None):
    return Transaction(
        transaction_id="CAT001",
        type=tx_type,
        amount=amount,
        counterparty_name=name,
        account_number=account,
        transaction_cost=cost,
        raw_sms="",
    )


class TestCategorize:
    def test_utilities_by_name(self):
        tx = _tx(name="KENYA POWER")
        assert categorize(tx) == "Utilities"

    def test_telecommunications_airtime(self):
        tx = _tx(tx_type="airtime")
        assert categorize(tx) == "Telecommunications"

    def test_food_by_name(self):
        tx = _tx(name="NAIVAS SUPERMARKET")
        assert categorize(tx) == "Food & Groceries"

    def test_financial_services_bank(self):
        tx = _tx(name="EQUITY BANK")
        assert categorize(tx) == "Financial Services"

    def test_government_kra(self):
        tx = _tx(name="KRA")
        assert categorize(tx) == "Government"

    def test_default_for_send(self):
        tx = _tx(tx_type="send", name="UNKNOWN PERSON")
        assert categorize(tx) == "Personal Transfer"

    def test_default_for_receive(self):
        tx = _tx(tx_type="receive")
        assert categorize(tx) == "Income"

    def test_default_for_withdraw(self):
        tx = _tx(tx_type="withdraw")
        assert categorize(tx) == "Cash Withdrawal"

    def test_default_for_deposit(self):
        tx = _tx(tx_type="deposit")
        assert categorize(tx) == "Cash Deposit"

    def test_default_for_paybill(self):
        tx = _tx(tx_type="paybill", name="UNKNOWN BILLER", account="999")
        assert categorize(tx) == "Bill Payment"

    def test_default_for_till(self):
        tx = _tx(tx_type="till", name="RANDOM SHOP")
        assert categorize(tx) == "Shopping"


class TestCategorizeAndApply:
    def test_sets_category_on_transaction(self):
        tx = _tx(name="KENYA POWER")
        result = categorize_and_apply(tx)
        assert result.category == "Utilities"
        assert tx.category == "Utilities"  # in-place


class TestTagTransaction:
    def test_high_value_tag(self):
        tx = _tx(amount=15_000)
        tag_transaction(tx)
        assert "high-value" in tx.tags

    def test_micro_tag(self):
        tx = _tx(amount=20)
        tag_transaction(tx)
        assert "micro" in tx.tags

    def test_debit_tag_for_send(self):
        tx = _tx(tx_type="send")
        tag_transaction(tx)
        assert "debit" in tx.tags

    def test_credit_tag_for_receive(self):
        tx = _tx(tx_type="receive")
        tag_transaction(tx)
        assert "credit" in tx.tags

    def test_has_fee_tag(self):
        tx = _tx(cost=14.0)
        tag_transaction(tx)
        assert "has-fee" in tx.tags

    def test_no_fee_tag_when_zero(self):
        tx = _tx(cost=0.0)
        tag_transaction(tx)
        assert "has-fee" not in tx.tags
