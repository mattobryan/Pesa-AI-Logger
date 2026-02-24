"""Tests for the SMS parsing engine."""

import pytest
from datetime import datetime

from pesa_logger.parser import parse_sms, Transaction


# ─── Sample SMS messages ─────────────────────────────────────────────────────

SEND_SMS = (
    "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)

RECEIVE_SMS = (
    "QZ89ABC Confirmed. You have received Ksh2,500.00 from JANE SMITH 0798765432 "
    "on 20/2/26 at 3:15 PM. New M-PESA balance is Ksh7,500.00."
)

PAYBILL_SMS = (
    "KL12MNO Confirmed. Ksh1,200.00 paid to KENYA POWER for account 123456 on 21/2/26 "
    "at 9:00 AM. New M-PESA balance is Ksh3,800.00. Transaction cost, Ksh28.00."
)

TILL_SMS = (
    "PQ34RST Confirmed. Ksh450.00 paid to NAIVAS SUPERMARKET on 21/2/26 at 11:45 AM."
    " New M-PESA balance is Ksh3,350.00. Transaction cost, Ksh9.00."
)

AIRTIME_SMS = (
    "VW56XYZ Confirmed. Ksh50.00 paid to Airtime on 21/2/26 at 8:00 AM."
    " New M-PESA balance is Ksh3,300.00."
)

WITHDRAW_SMS = (
    "AB78CDE Confirmed. Ksh500.00 withdrawn from agent on 19/2/26 at 2:00 PM."
    " New M-PESA balance is Ksh2,800.00. Transaction cost, Ksh22.00."
)

DEPOSIT_SMS = (
    "FG90HIJ Confirmed. Ksh3,000.00 deposited on 18/2/26 at 4:00 PM."
    " New M-PESA balance is Ksh5,800.00."
)

REVERSAL_SMS = (
    "XY12ZAB Confirmed. You have received Ksh500.00 from a reversal of Ksh500.00"
    " on 17/2/26 at 1:00 PM. New M-PESA balance is Ksh6,300.00."
)

INVALID_SMS = "Hello, how are you today?"

WITHDRAW_VARIANT_SMS = (
    "UBLGC7B1H1 Confirmed.on 21/2/26 at 1:42 PMWithdraw Ksh500.00 from "
    "323801 - Ndeche Communications Karuri Banana; New M-PESA balance is "
    "Ksh211.25. Transaction cost, Ksh29.00."
)

SEND_VARIANT_BALANCE_SPACE_SMS = (
    "UBK1Q7IUTZ Confirmed. Ksh10,500.00 sent to BRIAN  OMWAMBA 0725829629 "
    "on 20/2/26 at 4:59 PM. New M-PESA balance is Ksh 519.77. "
    "Transaction cost, Ksh100.00."
)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestParseSend:
    def test_returns_transaction(self):
        tx = parse_sms(SEND_SMS)
        assert tx is not None

    def test_type_is_send(self):
        tx = parse_sms(SEND_SMS)
        assert tx.type == "send"

    def test_transaction_id(self):
        tx = parse_sms(SEND_SMS)
        assert tx.transaction_id == "BC47YUI"

    def test_amount(self):
        tx = parse_sms(SEND_SMS)
        assert tx.amount == 1000.0

    def test_balance(self):
        tx = parse_sms(SEND_SMS)
        assert tx.balance == 5000.0

    def test_transaction_cost(self):
        tx = parse_sms(SEND_SMS)
        assert tx.transaction_cost == 14.0

    def test_counterparty_name(self):
        tx = parse_sms(SEND_SMS)
        assert tx.counterparty_name == "JOHN DOE"

    def test_counterparty_phone(self):
        tx = parse_sms(SEND_SMS)
        assert tx.counterparty_phone == "0712345678"

    def test_raw_sms_stored(self):
        tx = parse_sms(SEND_SMS)
        assert tx.raw_sms == SEND_SMS


class TestParseReceive:
    def test_type_is_receive(self):
        tx = parse_sms(RECEIVE_SMS)
        assert tx.type == "receive"

    def test_amount(self):
        tx = parse_sms(RECEIVE_SMS)
        assert tx.amount == 2500.0

    def test_counterparty(self):
        tx = parse_sms(RECEIVE_SMS)
        assert tx.counterparty_name == "JANE SMITH"
        assert tx.counterparty_phone == "0798765432"


class TestParsePaybill:
    def test_type_is_paybill(self):
        tx = parse_sms(PAYBILL_SMS)
        assert tx.type == "paybill"

    def test_amount(self):
        tx = parse_sms(PAYBILL_SMS)
        assert tx.amount == 1200.0

    def test_account_number(self):
        tx = parse_sms(PAYBILL_SMS)
        assert tx.account_number == "123456"

    def test_counterparty_name(self):
        tx = parse_sms(PAYBILL_SMS)
        assert "KENYA POWER" in (tx.counterparty_name or "")


class TestParseTill:
    def test_type_is_till(self):
        tx = parse_sms(TILL_SMS)
        assert tx.type == "till"

    def test_amount(self):
        tx = parse_sms(TILL_SMS)
        assert tx.amount == 450.0


class TestParseAirtime:
    def test_type_is_airtime(self):
        tx = parse_sms(AIRTIME_SMS)
        assert tx.type == "airtime"

    def test_amount(self):
        tx = parse_sms(AIRTIME_SMS)
        assert tx.amount == 50.0


class TestParseWithdraw:
    def test_type_is_withdraw(self):
        tx = parse_sms(WITHDRAW_SMS)
        assert tx.type == "withdraw"

    def test_amount(self):
        tx = parse_sms(WITHDRAW_SMS)
        assert tx.amount == 500.0

    def test_withdraw_variant_without_space_before_withdraw(self):
        tx = parse_sms(WITHDRAW_VARIANT_SMS)
        assert tx is not None
        assert tx.type == "withdraw"
        assert tx.transaction_id == "UBLGC7B1H1"
        assert tx.amount == 500.0
        assert tx.balance == 211.25
        assert tx.transaction_cost == 29.0


class TestParseSendVariants:
    def test_send_variant_with_balance_space_after_ksh(self):
        tx = parse_sms(SEND_VARIANT_BALANCE_SPACE_SMS)
        assert tx is not None
        assert tx.type == "send"
        assert tx.transaction_id == "UBK1Q7IUTZ"
        assert tx.amount == 10500.0
        assert tx.balance == 519.77
        assert tx.transaction_cost == 100.0


class TestParseDeposit:
    def test_type_is_deposit(self):
        tx = parse_sms(DEPOSIT_SMS)
        assert tx.type == "deposit"

    def test_amount(self):
        tx = parse_sms(DEPOSIT_SMS)
        assert tx.amount == 3000.0


class TestParseInvalid:
    def test_returns_none_for_invalid_sms(self):
        assert parse_sms(INVALID_SMS) is None

    def test_returns_none_for_empty(self):
        assert parse_sms("") is None


class TestToDict:
    def test_to_dict_has_expected_keys(self):
        tx = parse_sms(SEND_SMS)
        d = tx.to_dict()
        for key in ("transaction_id", "type", "amount", "balance", "currency"):
            assert key in d
