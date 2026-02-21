"""Operational monitoring utilities (heartbeat and silence alerts)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pesa_logger.database import get_last_sms_received_utc, log_heartbeat_check


def heartbeat_status(
    db_path: str = "pesa_logger.db",
    threshold_hours: float = 24.0,
    now_utc: Optional[datetime] = None,
    record: bool = True,
) -> dict:
    """Compute ingestion heartbeat status and optionally persist telemetry."""
    if threshold_hours <= 0:
        raise ValueError("threshold_hours must be > 0")

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    last_sms = get_last_sms_received_utc(db_path=db_path)
    silence_hours = None
    status = "ok"
    alert = False
    reason = "ingestion_active"

    if not last_sms:
        status = "alert"
        alert = True
        reason = "no_messages_received"
    else:
        last_dt = datetime.fromisoformat(last_sms).replace(tzinfo=timezone.utc)
        silence_hours = max(
            0.0, (now - last_dt).total_seconds() / 3600.0
        )
        if silence_hours > threshold_hours:
            status = "alert"
            alert = True
            reason = f"silence_exceeded_{threshold_hours:g}h"

    alert_message = None
    if alert:
        if silence_hours is None:
            alert_message = "No SMS has been received yet."
        else:
            alert_message = (
                f"No SMS received for {silence_hours:.2f}h "
                f"(threshold {threshold_hours:.2f}h)."
            )

    check_id = None
    if record:
        check_id = log_heartbeat_check(
            status=status,
            threshold_hours=threshold_hours,
            db_path=db_path,
            last_sms_received_utc=last_sms,
            silence_hours=silence_hours,
            alert_message=alert_message,
        )

    return {
        "status": status,
        "alert": alert,
        "reason": reason,
        "threshold_hours": threshold_hours,
        "last_sms_received_utc": last_sms,
        "silence_hours": silence_hours,
        "alert_message": alert_message,
        "checked_at_utc": now.replace(tzinfo=None).isoformat(),
        "heartbeat_check_id": check_id,
    }
