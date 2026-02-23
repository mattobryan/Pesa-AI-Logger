"""Tests for the Termux phone forwarder core logic."""

from datetime import datetime, timedelta, timezone

from phone_module.script import mpesa_forwarder as fwd


def test_matches_required_terms():
    text = "ABC Confirmed. Ksh1,000.00 sent via M-PESA."
    assert fwd.matches_required_terms(text, ["m-pesa", "confirmed", "ksh"]) is True
    assert fwd.matches_required_terms(text, ["m-pesa", "foobar"]) is False


def test_message_identity_key_stable():
    msg = {
        "_id": 10,
        "number": "MPESA",
        "body": "Confirmed Ksh100 M-PESA",
        "date": 1700000000000,
    }
    k1 = fwd.message_identity_key(msg)
    k2 = fwd.message_identity_key(msg)
    assert k1 == k2


def test_enqueue_new_messages_filters_and_dedup():
    config = dict(fwd.DEFAULT_CONFIG)
    state = fwd.default_state()
    messages = [
        {"_id": 1, "body": "A Confirmed. Ksh10 M-PESA", "date": 1700000000000},
        {"_id": 1, "body": "A Confirmed. Ksh10 M-PESA", "date": 1700000000000},
        {"_id": 2, "body": "Hello world", "date": 1700000005000},
    ]

    enqueued = fwd.enqueue_new_messages(messages, state, config)
    assert enqueued == 1
    assert len(state["queue"]) == 1


def test_process_queue_success(monkeypatch):
    config = dict(fwd.DEFAULT_CONFIG)
    state = fwd.default_state()
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    state["queue"] = [
        {
            "key": "k1",
            "sms": "A Confirmed. Ksh10 M-PESA",
            "sender": "MPESA",
            "sms_timestamp_utc": now_iso,
            "enqueued_at_utc": now_iso,
            "retries": 0,
            "last_error": None,
            "next_attempt_utc": now_iso,
        }
    ]

    def fake_post(endpoint_url, payload, timeout_seconds, api_key=""):
        return 201, '{"status":"saved"}'

    monkeypatch.setattr(fwd, "post_sms", fake_post)
    fwd.process_queue(state, config)
    assert len(state["queue"]) == 0
    assert state["stats"]["forwarded"] == 1


def test_process_queue_failure_schedules_retry(monkeypatch):
    config = dict(fwd.DEFAULT_CONFIG)
    state = fwd.default_state()
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    state["queue"] = [
        {
            "key": "k2",
            "sms": "B Confirmed. Ksh20 M-PESA",
            "sender": "MPESA",
            "sms_timestamp_utc": now_iso,
            "enqueued_at_utc": now_iso,
            "retries": 0,
            "last_error": None,
            "next_attempt_utc": now_iso,
        }
    ]

    def fake_post(endpoint_url, payload, timeout_seconds, api_key=""):
        return 503, "downstream unavailable"

    monkeypatch.setattr(fwd, "post_sms", fake_post)
    fwd.process_queue(state, config)
    assert len(state["queue"]) == 1
    item = state["queue"][0]
    assert item["retries"] == 1
    assert item["last_error"] == "http_status_503"
