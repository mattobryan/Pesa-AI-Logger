# Termux Forwarder (Pilot)

This is the fastest private-use path to forward M-Pesa SMS to your local ledger.

Note: Android app track is archived; this Termux script path is the active phone module.

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
   - If backend requires a key, set `api_key` to match `PESA_API_KEY` on the server.
   - Keep required terms as `m-pesa`, `confirmed`, `ksh`.

Verify effective runtime config and paths:

```bash
python mpesa_forwarder.py --print-config
```

This prints:
- actual config path being read
- actual state/log file paths
- effective endpoint URL

Quick sanity checks:

```bash
termux-sms-list -l 1
python mpesa_forwarder.py --once --dry-run
tail -n 50 runtime/forwarder.log
```

## Pull only phone files from Git (recommended)

Use sparse checkout so Termux downloads only `phone_module/script` instead of the whole repo.

1. Install required packages:

```bash
pkg update && pkg upgrade -y
pkg install -y git python termux-api
```

2. Clone repo metadata + checkout only script path:

```bash
git clone --filter=blob:none --no-checkout <REPO_URL> "$HOME/Pesa-AI-Logger"
cd "$HOME/Pesa-AI-Logger"
git sparse-checkout init --cone
git sparse-checkout set phone_module/script
git checkout main
cd phone_module/script
chmod +x bootstrap_sparse_checkout.sh update_sparse_checkout.sh start.sh run_once.sh
python mpesa_forwarder.py --init-config
```

3. Future updates (from inside `phone_module/script`):

```bash
./update_sparse_checkout.sh main
```

Only this path is kept in working tree:

- `phone_module/script/`

## Local-only secure mode

For laptop-only operation, keep the receiver local and avoid network exposure:

```bash
copy .env.example .env
python main.py serve --port 5000
```

Receiver binds to `127.0.0.1` only. Use direct local ingestion if the phone cannot reach localhost.

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

Suggested setup:

```bash
mkdir -p ~/.termux/boot
cp boot/start_forwarder.sh ~/.termux/boot/start_forwarder.sh
chmod +x ~/.termux/boot/start_forwarder.sh start.sh run_once.sh bootstrap_sparse_checkout.sh update_sparse_checkout.sh
```

If your forwarder folder is not `~/mpesa-forwarder` or `~/Pesa-AI-Logger/phone_module/script`,
set path explicitly in `~/.termux/boot/start_forwarder.sh`:

```bash
export FORWARDER_DIR="$HOME/your/path/to/phone_module/script"
```

After reboot, verify boot startup:

```bash
tail -n 100 runtime/boot.log
python mpesa_forwarder.py --print-config
```
