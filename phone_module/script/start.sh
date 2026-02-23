#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f config.json ]; then
  python mpesa_forwarder.py --init-config
fi

nohup python mpesa_forwarder.py >> runtime/nohup.log 2>&1 &
echo "Forwarder started in background."
