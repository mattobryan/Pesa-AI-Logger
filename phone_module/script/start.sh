#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p runtime

if [ ! -f config.json ]; then
  python mpesa_forwarder.py --init-config
fi

if command -v pgrep >/dev/null 2>&1; then
  if pgrep -f "mpesa_forwarder.py" >/dev/null 2>&1; then
    echo "Forwarder is already running."
    exit 0
  fi
fi

nohup python mpesa_forwarder.py >> runtime/nohup.log 2>&1 &
echo "Forwarder started in background."
