# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Raw-first ingestion orchestration in `pesa_logger/ingestion.py`.
- `inbox_sms` immutable capture table with normalized hash dedupe.
- `report_runs` table for traceable report/export execution.
- Parser metadata fields: `parser_version` and `parse_confidence`.
- `docs/IMPLEMENTATION_LOG.md` and `dev/README.md` workflow files.
- Heartbeat monitoring and no-SMS alert telemetry via `pesa_logger/monitoring.py`.
- Backup + scheduler automation via `pesa_logger/automation.py` and `scripts/`.
- Parser corpus validation tooling via `pesa_logger/corpus.py` and `corpus/mpesa_sms_corpus.jsonl`.
- Audited correction workflow via `transaction_corrections` + correction APIs/CLI.
- Phone pilot module at `phone_module/` with:
  - Termux forwarder script (`phone_module/script/mpesa_forwarder.py`)
  - example config, boot/start scripts, and runtime state queue
  - initial future APK placeholder (`phone_module/app/README.md`)
- Consolidated status report: `docs/PROJECT_STATUS_REPORT.md`.
- Tamper-evident append-only ledger chain table `ledger_chain` with hash continuity verification.
- New API endpoints:
  - `GET /inbox`
  - `GET /ledger/verify`
  - `GET /ledger/events`
- New CLI commands:
  - `list-inbox`
  - `reparse-failed`
  - `verify-ledger`
  - `ledger-events`
  - `rebuild-ledger`
- Forwarder historical import mode with paging:
  - `python mpesa_forwarder.py --once --backfill`
  - optional `--backfill-page-size` and `--backfill-max-pages`
- Forwarder SIM metadata capture in webhook source stamping (`sim:<slot>`, `sender:<origin>`).
- Fallback event-time ingestion from forwarder metadata (`sms_timestamp_utc`) when parser timestamp is missing.
- Ledger verifier now reports when historical data exists but `ledger_chain` is empty and recommends rebuild.
- One-time ledger backfill command to chain existing rows: `python main.py rebuild-ledger`.
- Parser hardening for SMS variants:
  - `Withdraw Ksh... from ...` format (including `...PMWithdraw...` concatenation)
  - balances formatted as `Ksh 519.77` (space after currency token)
- Inbox listing now supports parse-status filtering and failed-row reparse workflow.

### Changed
- `pesa_logger/database.py` migrated to canonical ledger schema and strict idempotency rules.
- `pesa_logger/webhook.py` now routes `/sms` through raw-first ingestion.
- `main.py` CLI `sms` command now uses the same ingestion pipeline.
- `pesa_logger/reports.py` now logs report runs and includes running balance in exports.
- `main.py` now includes commands for heartbeat, backup, scheduler, corpus validation, and corrections.
- `pesa_logger/webhook.py` now exposes monitoring and correction endpoints.
- Non-runtime report build utilities moved to `dev/tools/` to keep production/project tree clean.
- `pesa_logger/webhook.py` now stamps source metadata from forwarder payload meta and exposes inbox/ledger endpoints.
- `pesa_logger/database.py` now appends signed chain events for raw saves, canonical inserts, and corrections.
- `phone_module/script/mpesa_forwarder.py` now supports paged historical backfill and SIM slot capture.

### Roadmap Checklist
- [x] Heartbeat + silence alert monitor
- [x] Scheduler + daily backup automation
- [x] Larger parser corpus + validation gate
- [x] Audited correction workflow
- [x] Phone pilot forwarder module (Termux script)
- [x] Historical SMS backfill mode (paged import)
- [x] Tamper-evident ledger verification
