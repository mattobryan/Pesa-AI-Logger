# Pesa AI Logger

MPESA Hybrid AI Logger is a local-first financial logging and intelligence
system for mobile-money workflows.

It captures M-Pesa SMS notifications from Android, parses them through a Python
backend, stores structured records in SQLite, runs analytics and anomaly
detection, and can anchor Merkle roots to Polygon for tamper-evident audit
trails.

---

## Architecture

```text
Android Phone (Termux SMS Forwarder)
        |
POST /sms (authenticated webhook)
        |
Raw Inbox Persistence (inbox_sms)
        |
Parser + Canonical Ledger (transactions + ledger_chain)
        |
AI Analytics + Categorization + Anomaly Detection
        |
SQLite Database (pesa_logger.db)
        | \
        |  \-> Merkle Root -> Polygon PoS anchor
        |
Web Dashboard + CSV / Excel / Reports
```

---

## Feature Matrix

| Feature | Module |
|---|---|
| Regex M-Pesa SMS parser | `pesa_logger/parser.py` |
| SQLite storage and WAL mode | `pesa_logger/database.py` |
| Raw-first ingestion | `pesa_logger/ingestion.py` |
| Rule-based and AI categorization | `pesa_logger/categorizer.py` |
| Statistical and AI anomaly detection | `pesa_logger/anomaly.py` |
| AI analytics engine | `pesa_logger/ai_engine.py` |
| Forecasting and health score | `pesa_logger/analytics.py` |
| Weekly and monthly summaries | `pesa_logger/reports.py` |
| REST API and dashboard | `pesa_logger/webhook.py` |
| Heartbeat and silence alerting | `pesa_logger/monitoring.py` |
| Backup and scheduler helpers | `pesa_logger/automation.py` |
| Parser corpus validation | `pesa_logger/corpus.py` |
| Failed-message classification | `pesa_logger/failure_report.py` |
| Web3 Merkle anchoring | `pesa_logger/web3_anchor.py` |
| Termux phone forwarder | `phone_module/script/` |

---

## Supported SMS Types

| Type | Description |
|---|---|
| `send` | Money sent to another person |
| `receive` | Money received |
| `paybill` | Paybill payment |
| `till` | Lipa na M-Pesa till payment |
| `airtime` | Airtime purchase |
| `withdraw` | Agent withdrawal |
| `deposit` | Agent deposit |
| `reversal` | Transaction reversal |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure local environment

```bash
copy .env.example .env
```

Edit `.env` and set at minimum:

```text
PESA_API_KEY=your-secret
```

`.env` stays local and is ignored by git.

### 3. Start the server

```bash
python main.py serve --port 5000
```

The server binds to `127.0.0.1` by default.

### 4. Send a test SMS

```bash
curl -X POST http://localhost:5000/sms ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: your-secret" ^
  -d "{\"sms\": \"BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 21/2/26 at 10:30 AM. New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00.\"}"
```

---

## Docker

```bash
docker compose up
```

Data persists in the named volume `pesa_data`.

---

## CLI Reference

```bash
python main.py sms "<raw sms text>"
python main.py serve --port 5000
python main.py insights --days 30
python main.py summary --period monthly
python main.py export-csv --output transactions.csv
python main.py export-excel --output transactions.xlsx
python main.py anomalies --days 90
python main.py verify-ledger
python main.py ledger-events --limit 20
python main.py rebuild-ledger
python main.py list-inbox --oldest-first --limit 500
python main.py list-inbox --parse-status failed --limit 200
python main.py list-transactions --sim-slot 2 --limit 200
python main.py reparse-failed --limit 200
python main.py failed-report --limit 5000 --sample-size 3
python main.py correct --transaction-id BC47YUI --set category=Utilities --reason "manual fix" --by admin
python main.py list-corrections --transaction-id BC47YUI
python main.py heartbeat --hours 24
python main.py backup --backup-dir backups --keep-last 14
python main.py scheduler-once --backup-dir backups --export-dir exports --hours 24
python main.py validate-corpus --path corpus/mpesa_sms_corpus.jsonl --min-success 0.98
python scripts/live_pilot.py
```

---

## API Endpoints

When `PESA_API_KEY` is set, data and analytics routes require either an
`X-API-Key` header or an authenticated dashboard session.

### Core

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Public health check |
| `GET` | `/dashboard` | Dashboard shell |
| `POST` | `/auth` | Dashboard login |
| `GET` | `/logout` | Dashboard logout |
| `GET` | `/health/details` | Detailed diagnostics |
| `GET` | `/routes` | Live route inventory |
| `POST` | `/sms` | Ingest a raw M-Pesa SMS |

### Data and Analytics

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | List stored transactions |
| `GET` | `/inbox` | List raw inbox rows |
| `GET` | `/inbox/failed/report` | Failed-message classification |
| `GET` | `/analytics/insights` | Narrative insights |
| `GET` | `/analytics/summary/weekly` | Weekly summary |
| `GET` | `/analytics/summary/monthly` | Monthly summary |
| `GET` | `/analytics/anomalies` | Detected anomalies |
| `GET` | `/export/csv` | CSV export |
| `GET` | `/monitor/heartbeat` | Heartbeat status |
| `GET` | `/monitor/heartbeat/history` | Heartbeat history |
| `POST` | `/corrections` | Apply audited correction |
| `GET` | `/corrections` | List correction history |

### Ledger and Web3

| Method | Path | Description |
|---|---|---|
| `GET` | `/ledger/verify` | Verify local hash-chain integrity |
| `GET` | `/ledger/events` | List ledger events |
| `POST` | `/ledger/anchor` | Trigger Merkle anchor |
| `GET` | `/ledger/anchors` | List anchor records |
| `GET` | `/ledger/verify-onchain` | Verify root on-chain |
| `GET` | `/ledger/anchor-summary` | Anchor summary for dashboard |

---

## AI Providers

Set `AI_PROVIDER` in `.env` to one of:

| Value | Description |
|---|---|
| `stub` | Offline mode, safe for tests and CI |
| `openai` | OpenAI API |
| `anthropic` | Anthropic API |
| `ollama` | Local Ollama server |

---

## Web3 Anchoring

Anchoring is disabled by default. When enabled, the app computes a SHA-256
Merkle root from pending ledger hashes and stores or publishes that root to the
`PesaAnchor` contract.

Example `.env` settings:

```text
WEB3_ENABLED=true
POLYGON_RPC_URL=https://polygon-rpc.com
WALLET_PRIVATE_KEY=0x...
CONTRACT_ADDRESS=0x...
ANCHOR_EVERY_N=10
```

`POLYGON_RPC_URL` may point to mainnet or Amoy. The code now derives the chain
ID and explorer URL from the RPC host.

---

## Deployment

The repo includes:

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage runtime image |
| `docker-compose.yml` | Local container run with persistence |
| `render.yaml` | Render deployment manifest |
| `.github/workflows/ci.yml` | Test, audit, and Docker CI |

---

## Running Tests

```bash
pytest tests/ -v

set AI_PROVIDER=stub && set PESA_DB_PATH=:memory: && pytest tests/ -v
```

Current suite: **204 tests** across **16 test files**.

---

## Project Structure

```text
pesa_logger/
|-- __init__.py
|-- ai_engine.py
|-- analytics.py
|-- anomaly.py
|-- automation.py
|-- categorizer.py
|-- corpus.py
|-- dashboard.py
|-- database.py
|-- failure_report.py
|-- ingestion.py
|-- monitoring.py
|-- parser.py
|-- reports.py
|-- web3_anchor.py
|-- webhook.py
`-- prompts/
    |-- __init__.py
    |-- anomaly_explain.txt
    |-- category_suggest.txt
    |-- insights.txt
    `-- spending_coach.txt
contracts/
`-- PesaAnchor.sol
tests/
|-- test_anomaly.py
|-- test_automation.py
|-- test_categorizer.py
|-- test_corpus.py
|-- test_corrections.py
|-- test_database.py
|-- test_failure_report.py
|-- test_ingestion.py
|-- test_ledger.py
|-- test_monitoring.py
|-- test_parser.py
|-- test_phone_forwarder.py
|-- test_reports.py
|-- test_web3_anchor.py
|-- test_webhook.py
`-- test_webhook_ledger.py
scripts/
|-- backup_db.py
|-- live_pilot.py
`-- run_scheduler_once.py
phone_module/
|-- script/
`-- app/
.github/workflows/ci.yml
Dockerfile
docker-compose.yml
render.yaml
requirements.txt
.env.example
main.py
```

---

## Tech Stack

- Python 3.11+
- SQLite with WAL mode
- Flask
- OpenAI / Anthropic / Ollama
- openpyxl
- pytest and pytest-cov
- Docker and Docker Compose
- GitHub Actions
- Render

---

## Version

`v1.0.0`
