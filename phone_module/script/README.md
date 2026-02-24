# Termux Forwarder (Pilot)

This is the fastest private-use path to forward M-Pesa SMS to your local ledger.

## What it does

- Polls SMS inbox with `termux-sms-list`
- Supports one-time historical backfill mode (paged import)
- Filters messages containing required terms
- Forwards to `POST /sms`
- Retries failed deliveries with backoff
- Persists local queue/state

## Prerequisites on phone

1. Install `Termux` and `Termux:API`.
2. In Termux:
   - `pkg update && pkg upgrade -y`
   - `pkg install -y python termux-api`
3. Grant SMS permission:
   - `termux-setup-storage`
   - Android settings -> Apps -> Termux -> Permissions -> allow SMS
4. Disable battery optimization for Termux and Termux:API.

## Setup

1. Copy this folder to your phone (e.g. `~/mpesa-forwarder`).
2. Create config:
   - `python mpesa_forwarder.py --init-config`
3. Edit `config.json`:
   - Set `endpoint_url` to your backend `/sms` URL.
   - Keep required terms as `m-pesa`, `confirmed`, `ksh`.

Verify effective runtime config and paths:

```bash
python mpesa_forwarder.py --print-config
```

This prints:
- actual config path being read
- actual state/log file paths
- effective endpoint URL

## Run

Single cycle test:

```bash
python mpesa_forwarder.py --once
```

One-time full historical backfill:

```bash
python mpesa_forwarder.py --once --backfill
```

Optional tuning:

```bash
python mpesa_forwarder.py --once --backfill --backfill-page-size 200 --backfill-max-pages 150
```

Daemon mode:

```bash
python mpesa_forwarder.py
```

Files created:

- `runtime/state.json`
- `runtime/forwarder.log`

## Boot startup (optional)

Use `Termux:Boot` and place a boot script under `~/.termux/boot/`.
See `boot/start_forwarder.sh` in this folder.
