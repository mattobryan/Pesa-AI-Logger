# Pesa AI Logger

**MPESA Hybrid AI Logger** — a local-first financial logging and intelligence system for mobile-money-driven environments.

The system captures M-Pesa SMS notifications, parses them through a Python backend, stores structured records in SQLite, and provides automated analytics, anomaly detection, and reporting.

---

## Architecture

```
Android Phone (SMS Forwarder)
        ↓
Forwarded SMS (Webhook / HTTP POST)
        ↓
Raw Inbox Persistence (inbox_sms)
        ↓
Parser + Canonical Ledger (transactions)
        ↓
Python Intelligence Engine (pesa_logger/)
        ↓
SQLite Database  (pesa_logger.db)
        ↓
Excel / CSV Export  +  Financial Analytics
```

---

## Features

| Feature | Module |
|---------|--------|
| Regex-based M-Pesa SMS parser | `pesa_logger/parser.py` |
| SQLite transaction storage | `pesa_logger/database.py` |
| Transaction categorization | `pesa_logger/categorizer.py` |
| Anomaly detection | `pesa_logger/anomaly.py` |
| Weekly / monthly summaries | `pesa_logger/reports.py` |
| CSV and Excel export | `pesa_logger/reports.py` |
| REST webhook / API server | `pesa_logger/webhook.py` |
| AI-generated insights | `pesa_logger/analytics.py` |
| Raw-first ingestion orchestration | `pesa_logger/ingestion.py` |
| Heartbeat and silence alerts | `pesa_logger/monitoring.py` |
| Backup and scheduler automation | `pesa_logger/automation.py` |
| Parser corpus validation | `pesa_logger/corpus.py` |
| Audited transaction corrections | `pesa_logger/database.py` + `/corrections` |
| Tamper-evident hash-chain ledger | `pesa_logger/database.py` + `/ledger/*` |
| Phone-side pilot forwarder (Termux) | `phone_module/script/` |

---

## Supported SMS Types

- **send** — money sent to another person
- **receive** — money received from another person
- **paybill** — payment to a paybill number (e.g. KPLC, DSTV)
- **till** — Lipa na M-Pesa till payment
- **airtime** — airtime purchase
- **withdraw** — agent withdrawal
- **deposit** — agent deposit
- **reversal** — transaction reversal

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Parse and store a single SMS

```bash
python main.py sms "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM. New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00."
```

Output:
```json
{
  "transaction_id": "BC47YUI",
  "type": "send",
  "amount": 1000.0,
  "currency": "KES",
  "counterparty_name": "JOHN DOE",
  "counterparty_phone": "0712345678",
  "balance": 5000.0,
  "transaction_cost": 14.0,
  "timestamp": "2026-02-21T10:30:00",
  "category": "Personal Transfer",
  "tags": ["debit", "has-fee"]
}
```

### 3. Start the webhook server

```bash
python main.py serve --port 5000
```

Send an SMS via HTTP POST:
```bash
curl -X POST http://localhost:5000/sms \
     -H "Content-Type: application/json" \
     -d '{"sms": "BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE ..."}'
```

### 4. View financial insights

```bash
python main.py insights --days 30
```

### 5. Generate monthly summary

```bash
python main.py summary --period monthly
```

### 6. Export to CSV

```bash
python main.py export-csv --output transactions.csv
```

### 7. Export to Excel

```bash
python main.py export-excel --output transactions.xlsx
```

### 8. Detect anomalies

```bash
python main.py anomalies --days 90
```

### 9. Run heartbeat monitor

```bash
python main.py heartbeat --hours 24
```

### 10. Create DB backup

```bash
python main.py backup --backup-dir backups --keep-last 14
```

### 11. Run one scheduler cycle

```bash
python main.py scheduler-once --backup-dir backups --export-dir exports --hours 24
```

### 12. Validate parser corpus

```bash
python main.py validate-corpus --path corpus/mpesa_sms_corpus.jsonl --min-success 0.98
```

### 13. Apply audited correction

```bash
python main.py correct --transaction-id BC47YUI --set category=Utilities --reason "manual correction" --by admin
```

### 14. Run phone pilot forwarder (Termux)

See:

```bash
phone_module/script/README.md
```

### 15. List raw inbox SMS (oldest first)

```bash
python main.py list-inbox --oldest-first --limit 500
```

### 16. Verify tamper-evident ledger chain

```bash
python main.py verify-ledger
python main.py ledger-events --limit 20
```

If the chain is empty but your DB already has historical records, run one-time backfill:

```bash
python main.py rebuild-ledger
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/sms` | Ingest a raw M-Pesa SMS |
| `GET` | `/transactions` | List stored transactions |
| `GET` | `/analytics/insights` | AI-generated insights |
| `GET` | `/analytics/summary/weekly` | Weekly summary |
| `GET` | `/analytics/summary/monthly` | Monthly summary |
| `GET` | `/analytics/anomalies` | Detected anomalies |
| `GET` | `/export/csv` | Download CSV export |
| `GET` | `/monitor/heartbeat` | Heartbeat and silence status |
| `GET` | `/monitor/heartbeat/history` | Heartbeat telemetry history |
| `POST` | `/corrections` | Apply audited correction |
| `GET` | `/corrections` | List correction audit history |
| `GET` | `/inbox` | List raw stored SMS rows |
| `GET` | `/ledger/verify` | Verify hash-chain integrity |
| `GET` | `/ledger/events` | List hash-chain ledger events |

---

## Optional AI Narrative (OpenAI)

Set `OPENAI_API_KEY` in your environment to enable LLM-generated narrative summaries in the insights endpoint.

```bash
export OPENAI_API_KEY=sk-...
python main.py serve
```

---

## Project Structure

```
pesa_logger/
├── __init__.py       # Package metadata
├── ingestion.py      # Raw-first ingestion workflow
├── monitoring.py     # Heartbeat + silence alert logic
├── automation.py     # Backup + scheduled cycle helpers
├── corpus.py         # Corpus loader and parser validator
├── parser.py         # Regex-based SMS parsing engine
├── database.py       # SQLite storage layer
├── categorizer.py    # Rule-based categorization + tagging
├── anomaly.py        # Statistical anomaly detection
├── reports.py        # CSV / Excel export & financial summaries
├── analytics.py      # Cashflow trends, insights, top categories
└── webhook.py        # Flask REST API / webhook server
tests/
├── test_parser.py
├── test_corpus.py
├── test_database.py
├── test_corrections.py
├── test_categorizer.py
├── test_anomaly.py
├── test_automation.py
├── test_monitoring.py
├── test_reports.py
└── test_webhook.py
scripts/
├── backup_db.py
└── run_scheduler_once.py
corpus/
└── mpesa_sms_corpus.jsonl
phone_module/
├── app/
└── script/
main.py               # CLI entry point
requirements.txt
docs/IMPLEMENTATION_LOG.md
dev/README.md
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Tech Stack

- Python 3.10+
- SQLite (via `sqlite3` stdlib)
- Flask (webhook API)
- openpyxl (Excel export)
- pytest (testing)
- OpenAI API (optional AI narrative)

---

## Version

`v0.3.0`

## Tags

`python` · `fintech` · `mpesa` · `sms-parser` · `automation` · `personal-finance` · `sqlite` · `data-logging` · `ai-agent` · `kenya-tech`

