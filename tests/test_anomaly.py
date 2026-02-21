"""Tests for the anomaly detection module."""

import pytest
from datetime import datetime, timedelta

from pesa_logger.anomaly import (
    detect_large_transaction,
    detect_rapid_successive,
    detect_unusual_hour,
)


def _make_row(tid="TX001", tx_type="send", amount=500.0, timestamp=None):
    ts = timestamp or datetime(2026, 2, 21, 10, 30).isoformat()
    return {
        "transaction_id": tid,
        "type": tx_type,
        "amount": amount,
        "timestamp": ts,
    }


class TestDetectLargeTransaction:
    def _baseline(self, n=10, amount=500.0, tx_type="send"):
        return [_make_row(f"B{i}", tx_type=tx_type, amount=amount) for i in range(n)]

    def test_flags_large_amount(self):
        baseline = self._baseline()
        big_tx = _make_row("BIG", amount=50_000.0)
        result = detect_large_transaction(big_tx, baseline + [big_tx])
        assert result is not None
        assert result.transaction_id == "BIG"

    def test_no_flag_for_normal_amount(self):
        # Use a baseline with variance so that 600 is well within the normal range
        baseline = [
            _make_row(f"B{i}", tx_type="send", amount=a)
            for i, a in enumerate([400, 450, 500, 550, 600, 480, 520, 490, 510, 470])
        ]
        normal_tx = _make_row("NORM", amount=600.0)
        result = detect_large_transaction(normal_tx, baseline)
        assert result is None

    def test_returns_none_insufficient_history(self):
        only_one = [_make_row("S1", amount=500.0)]
        result = detect_large_transaction(only_one[0], only_one)
        assert result is None


class TestDetectUnusualHour:
    def test_flags_midnight_transaction(self):
        tx = _make_row(timestamp=datetime(2026, 2, 21, 2, 0).isoformat())
        result = detect_unusual_hour(tx)
        assert result is not None
        assert "unusual hour" in result.reason.lower()

    def test_no_flag_for_daytime(self):
        tx = _make_row(timestamp=datetime(2026, 2, 21, 10, 0).isoformat())
        result = detect_unusual_hour(tx)
        assert result is None

    def test_no_flag_when_no_timestamp(self):
        tx = _make_row()
        tx["timestamp"] = None
        result = detect_unusual_hour(tx)
        assert result is None


class TestDetectRapidSuccessive:
    def test_flags_burst(self):
        base = datetime(2026, 2, 21, 10, 0)
        txs = [
            _make_row(f"R{i}", tx_type="send", timestamp=(base + timedelta(minutes=i)).isoformat())
            for i in range(5)
        ]
        result = detect_rapid_successive(txs, window_minutes=10, threshold_count=3)
        assert len(result) >= 1

    def test_no_flag_for_sparse_transactions(self):
        base = datetime(2026, 2, 21, 10, 0)
        txs = [
            _make_row(f"S{i}", tx_type="send", timestamp=(base + timedelta(hours=i * 3)).isoformat())
            for i in range(5)
        ]
        result = detect_rapid_successive(txs, window_minutes=10, threshold_count=3)
        assert len(result) == 0
