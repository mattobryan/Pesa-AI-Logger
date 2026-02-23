#!/data/data/com.termux/files/usr/bin/bash
set -eu

sleep 20

FORWARDER_DIR="$HOME/mpesa-forwarder"
cd "$FORWARDER_DIR"

mkdir -p runtime
nohup python mpesa_forwarder.py >> runtime/boot.log 2>&1 &
