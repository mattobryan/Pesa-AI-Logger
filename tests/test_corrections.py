"""Tests for audited transaction corrections."""

import pytest

from pesa_logger.database import (
    apply_transaction_correction,
    close_connection,
    get_transaction,
    init_db,
    list_transaction_corrections,
)
from pesa_logger.ingestion import ingest_sms_text


SEND_SMS = (
    "COR001 Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM."
    " New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "corrections_test.db")
    init_db(path)
    ingest_sms_text(SEND_SMS, db_path=path, source="test")
    yield path
    close_connection(path)


def test_apply_correction_updates_transaction_and_logs_audit(db):
    result = apply_transaction_correction(
        transaction_id="COR001",
        updates={"category": "Utilities", "counterparty_name": "JOHN D."},
        reason="Name normalization + manual category",
        corrected_by="tester",
        db_path=db,
    )
    assert result["status"] == "updated"
    assert "category" in result["changes"]

    tx = get_transaction("COR001", db_path=db)
    assert tx["category"] == "Utilities"
    assert tx["counterparty_name"] == "JOHN D."

    rows = list_transaction_corrections(db_path=db, transaction_id="COR001")
    assert len(rows) >= 2


def test_apply_correction_rejects_unknown_field(db):
    with pytest.raises(ValueError):
        apply_transaction_correction(
            transaction_id="COR001",
            updates={"unknown_field": "x"},
            reason="invalid",
            corrected_by="tester",
            db_path=db,
        )
