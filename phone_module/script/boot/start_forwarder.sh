#!/data/data/com.termux/files/usr/bin/bash
set -eu

sleep 20

if [ -n "${FORWARDER_DIR:-}" ] && [ -f "${FORWARDER_DIR}/mpesa_forwarder.py" ]; then
  TARGET_DIR="${FORWARDER_DIR}"
elif [ -f "$HOME/mpesa-forwarder/mpesa_forwarder.py" ]; then
  TARGET_DIR="$HOME/mpesa-forwarder"
elif [ -f "$HOME/Pesa-AI-Logger/phone_module/script/mpesa_forwarder.py" ]; then
  TARGET_DIR="$HOME/Pesa-AI-Logger/phone_module/script"
else
  mkdir -p "$HOME/.termux/boot/logs"
  echo "$(date -u +%FT%TZ) forwarder_dir_not_found" >> "$HOME/.termux/boot/logs/forwarder_boot_error.log"
  exit 1
fi

cd "$TARGET_DIR"

mkdir -p runtime
if [ ! -f config.json ]; then
  python mpesa_forwarder.py --init-config >> runtime/boot.log 2>&1
fi

if command -v pgrep >/dev/null 2>&1; then
  if pgrep -f "mpesa_forwarder.py" >/dev/null 2>&1; then
    echo "$(date -u +%FT%TZ) forwarder_already_running" >> runtime/boot.log
    exit 0
  fi
fi

nohup python mpesa_forwarder.py >> runtime/boot.log 2>&1 &
echo "$(date -u +%FT%TZ) forwarder_started pid=$!" >> runtime/boot.log
