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
  - archived Android app-track folder (`phone_module/app/README.md`)
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
- Failed-message classification reporting module (`pesa_logger/failure_report.py`) with deterministic receipt-family grouping.
- New CLI commands/filters for forensic operations:
  - `failed-report`
  - `list-transactions`
  - `--sim-slot` support on `list-inbox`
- New API capabilities:
  - `GET /inbox/failed/report`
  - `sim_slot` filtering on `/inbox` and `/transactions`
- SIM-slot extraction in query outputs (`sim_slot`) from stamped source metadata (`sim:<slot>`).
- Live HTTP smoke-test script: `scripts/live_pilot.py`.
- Optional API-key auth for ingestion endpoint (`X-API-Key`) via `create_app(..., api_key=...)` / `main.py serve --api-key`.
- `main.py serve` defaults to localhost-only binding for laptop-first secure operation.
- Authenticated diagnostics endpoint `GET /health/details` (API key or dashboard session when auth is enabled).
- Live route inventory endpoint `GET /routes` for runtime route/method/auth metadata.
- End-to-end dashboard/session-aware auth guards across data APIs (`/transactions`, `/inbox`, analytics, ledger, corrections, monitoring, export).

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
- `pesa_logger/database.py` now supports SIM-slot filtered inbox/transaction queries using source metadata tokens.
- `pesa_logger/webhook.py` now exposes failed-inbox classification reporting and SIM-slot query filters.
- `pesa_logger/webhook.py` now reports `api_key_required` on `/health/details`.
- `phone_module/script/README.md` now documents local-only secure mode and API-key usage.
- `pesa_logger/webhook.py` now uses non-static session secrets and hardened session-cookie defaults.
- `pesa_logger/dashboard.py` now escapes dynamic HTML content before DOM insertion to reduce XSS risk.
- `GET /health` now returns minimal public status, with detailed diagnostics moved to `GET /health/details`.
- Dashboard API reference now renders live route data from `GET /routes` instead of static route text.
- `main.py serve` now supports explicit `--host` and defaults to loopback (`127.0.0.1`) unless overridden.
- Root `runtime/` logs are now ignored in `.gitignore` to prevent accidental commits.
- Project direction is now Termux-only for phone forwarding; Android app track is archived/inactive.

### Roadmap Checklist
- [x] Heartbeat + silence alert monitor
- [x] Scheduler + daily backup automation
- [x] Larger parser corpus + validation gate
- [x] Audited correction workflow
- [x] Phone pilot forwarder module (Termux script)
- [x] Historical SMS backfill mode (paged import)
- [x] Tamper-evident ledger verification
- [x] Failed-message classification reporting
- [x] SIM-slot transaction/inbox separation filters
