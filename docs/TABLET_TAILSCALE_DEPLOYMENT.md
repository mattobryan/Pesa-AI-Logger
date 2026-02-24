# Tablet Tailscale Deployment Runbook

This runbook deploys the live receiver on a tablet and allows only your phone forwarder to reach it through Tailscale.

## 1) Target topology

- Phone forwarder posts SMS to: `http://<tablet_tailscale_ip>:5000/sms`
- Receiver runs on tablet with:
  - host bound to tablet Tailscale IP
  - API key required on `/sms`
- No public internet port exposure

## 2) Tablet setup

1. Install:
   - Tailscale app
   - Python 3.10+
2. Join tablet to your tailnet.
3. Clone repo on tablet and install deps:

```bash
git clone https://github.com/mattobryan/Pesa-AI-Logger
cd Pesa-AI-Logger
pip install -r requirements.txt
```

4. Find tablet Tailscale IPv4:

```bash
tailscale ip -4
```

Assume result: `100.101.102.103`.

## 3) Start receiver on tablet (locked)

Generate a strong API key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run receiver bound to Tailscale interface only:

```bash
python main.py serve \
  --host 100.101.102.103 \
  --port 5000 \
  --api-key "PASTE_STRONG_KEY_HERE" \
  --db pesa_logger.db
```

Important:
- Do not use `--host 0.0.0.0` for this private setup.
- Keep this process running (tmux/screen/service).

## 4) Configure phone forwarder to tablet

Edit `phone_module/script/config.json` on phone:

```json
{
  "endpoint_url": "http://100.101.102.103:5000/sms",
  "source": "android-termux",
  "api_key": "PASTE_STRONG_KEY_HERE",
  "required_terms": ["m-pesa", "confirmed", "ksh"],
  "poll_interval_seconds": 30,
  "fetch_limit": 50,
  "backfill_page_size": 200,
  "backfill_max_pages": 100,
  "max_processed_keys": 5000,
  "retry_base_seconds": 15,
  "retry_max_seconds": 900,
  "max_retries": 0,
  "request_timeout_seconds": 15,
  "success_status_codes": [200, 201, 422]
}
```

Validate config path + endpoint in use:

```bash
python mpesa_forwarder.py --print-config
```

## 5) Connectivity test

From phone (Termux):

```bash
curl -i http://100.101.102.103:5000/health
```

Expected JSON includes:
- `"status": "ok"`
- `"api_key_required": true`

Then run one cycle:

```bash
python mpesa_forwarder.py --once
```

On tablet, confirm receipt:

```bash
python main.py list-inbox --limit 5
python main.py verify-ledger
```

## 6) Restrict access in Tailscale ACL

Use tags (recommended):

1. Tag tablet as `tag:mpesa-receiver`
2. Tag phone as `tag:mpesa-phone`

Policy example:

```json
{
  "tagOwners": {
    "tag:mpesa-receiver": ["autogroup:admin"],
    "tag:mpesa-phone": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:mpesa-phone"],
      "dst": ["tag:mpesa-receiver:5000"]
    }
  ]
}
```

This allows only tagged phone devices to reach receiver port `5000`.

## 7) Operational notes

- If tablet sleeps aggressively, keep charger connected and disable battery optimization for your runtime app.
- Keep a backup receiver path (laptop) for failover.
- Keep API key private and rotate if exposed.
