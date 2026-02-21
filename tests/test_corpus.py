"""Tests for parser corpus loader and validator."""

from pathlib import Path

from pesa_logger.corpus import load_corpus, validate_corpus


def test_load_corpus_reads_entries():
    path = "corpus/mpesa_sms_corpus.jsonl"
    entries = load_corpus(path)
    assert len(entries) >= 20
    assert "sms" in entries[0]


def test_validate_corpus_passes_gate():
    path = "corpus/mpesa_sms_corpus.jsonl"
    result = validate_corpus(path=path, min_success_rate=0.95)
    assert result["total"] >= 20
    assert result["passed_gate"] is True
    assert result["success_rate"] >= 0.95
