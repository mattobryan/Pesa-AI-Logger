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
Python Logging Engine  (pesa_logger/)
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
├── parser.py         # Regex-based SMS parsing engine
├── database.py       # SQLite storage layer
├── categorizer.py    # Rule-based categorization + tagging
├── anomaly.py        # Statistical anomaly detection
├── reports.py        # CSV / Excel export & financial summaries
├── analytics.py      # Cashflow trends, insights, top categories
└── webhook.py        # Flask REST API / webhook server
tests/
├── test_parser.py
├── test_database.py
├── test_categorizer.py
├── test_anomaly.py
├── test_reports.py
└── test_webhook.py
main.py               # CLI entry point
requirements.txt
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

`v0.1-hybrid-engine`

## Tags

`python` · `fintech` · `mpesa` · `sms-parser` · `automation` · `personal-finance` · `sqlite` · `data-logging` · `ai-agent` · `kenya-tech`

