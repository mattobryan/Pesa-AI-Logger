# Pesa AI Logger

**MPESA Hybrid AI Logger** — a local-first financial logging and intelligence system for mobile-money-driven environments.

The system captures M-Pesa SMS notifications, parses them through a Python backend, stores structured records in SQLite, and provides automated analytics, anomaly detection, and reporting.

---

## Architecture

```
Android Phone (Termux SMS Forwarder)
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
| Failed-message classification reports | `pesa_logger/failure_report.py` + `/inbox/failed/report` |
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

Optional local secret setup (recommended):

```bash
copy .env.example .env
```

Edit `.env` and set `PESA_API_KEY=...`.

```bash
python main.py serve --port 5000 --api-key "your-secret"
```

Or, when `PESA_API_KEY` is set in `.env`, start without passing the key each time:

```bash
python main.py serve --port 5000
```

The server binds to `127.0.0.1` by default.
Use `--host 0.0.0.0` when you intentionally need LAN/Tailscale/device access.

Send an SMS via HTTP POST:
```bash
curl -X POST http://localhost:5000/sms \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-secret" \
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

List only failed parse rows:

```bash
python main.py list-inbox --parse-status failed --limit 200
```

Reparse failed rows after parser updates:

```bash
python main.py reparse-failed --limit 200
```

Classify failed rows into receipt families (Fuliza, airtime, merchant acknowledgements, unknown):

```bash
python main.py failed-report --limit 5000 --sample-size 3
```

Filter inbox rows by SIM slot:

```bash
python main.py list-inbox --sim-slot 1 --limit 200
```

List canonical transactions filtered by SIM slot:

```bash
python main.py list-transactions --sim-slot 2 --limit 200
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

### 17. Run local live pilot (HTTP ingest smoke test)

```bash
python scripts/live_pilot.py
```

---

## API Endpoints

When `PESA_API_KEY` is configured, all data/analytics/ledger/export routes require either:
- `X-API-Key` header, or
- an authenticated dashboard session.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/dashboard` | Dashboard login/app shell (session-based) |
| `POST` | `/auth` | Dashboard login (API key -> session) |
| `GET` | `/logout` | Dashboard logout (clears session) |
| `GET` | `/health/details` | Detailed health diagnostics (auth) |
| `GET` | `/routes` | Live route inventory for dashboard/API clients (auth) |
| `POST` | `/sms` | Ingest a raw M-Pesa SMS (requires `X-API-Key` when configured) |
| `GET` | `/transactions` | List stored transactions (`type`, `category`, `sim_slot`, `limit`) |
| `GET` | `/analytics/insights` | AI-generated insights |
| `GET` | `/analytics/summary/weekly` | Weekly summary |
| `GET` | `/analytics/summary/monthly` | Monthly summary |
| `GET` | `/analytics/anomalies` | Detected anomalies |
| `GET` | `/export/csv` | Download CSV export |
| `GET` | `/monitor/heartbeat` | Heartbeat and silence status |
| `GET` | `/monitor/heartbeat/history` | Heartbeat telemetry history |
| `POST` | `/corrections` | Apply audited correction |
| `GET` | `/corrections` | List correction audit history |
| `GET` | `/inbox` | List raw stored SMS rows (`parse_status`, `sim_slot`, `limit`) |
| `GET` | `/inbox/failed/report` | Classify and summarize failed parse rows |
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
├── __init__.py
├── ai_engine.py
├── analytics.py
├── anomaly.py
├── automation.py
├── categorizer.py
├── corpus.py
├── dashboard.py
├── database.py
├── failure_report.py
├── ingestion.py
├── monitoring.py
├── parser.py
├── reports.py
├── web3_anchor.py
├── webhook.py
└── prompts/
    ├── __init__.py
    ├── anomaly_explain.txt
    ├── category_suggest.txt
    ├── insights.txt
    └── spending_coach.txt
contracts/
└── PesaAnchor.sol
tests/
├── test_anomaly.py
├── test_automation.py
├── test_categorizer.py
├── test_corpus.py
├── test_corrections.py
├── test_database.py
├── test_failure_report.py
├── test_ingestion.py
├── test_ledger.py
├── test_monitoring.py
├── test_parser.py
├── test_phone_forwarder.py
├── test_reports.py
└── test_webhook.py
scripts/
├── backup_db.py
├── live_pilot.py
└── run_scheduler_once.py
corpus/
└── mpesa_sms_corpus.jsonl
phone_module/
├── script/            # Active Termux forwarder
└── app/               # Archived Android app track
.github/workflows/ci.yml
Dockerfile
docker-compose.yml
render.yaml
main.py
requirements.txt
.env.example
```

---

## Running Tests

```bash
pytest tests/ -v

# CI-equivalent env for the test job
# (do not set PESA_API_KEY globally in this run)
set AI_PROVIDER=stub && set PESA_DB_PATH=:memory: && pytest tests/ -v
```

Current suite: **154 tests** across **14 test files**.

---

## Tech Stack

- Python 3.11+
- SQLite (`sqlite3`, WAL mode)
- Flask
- openpyxl
- OpenAI / Anthropic / Ollama (optional providers)
- pytest + pytest-cov
- Docker + docker compose
- GitHub Actions (tests, security audit, Docker build check)
- Render (deployment target)

---

## Version

`v0.4.1`

## Tags

`python` · `fintech` · `mpesa` · `sms-parser` · `automation` · `personal-finance` · `sqlite` · `data-logging` · `ai-agent` · `kenya-tech`
