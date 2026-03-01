#!/data/data/com.termux/files/usr/bin/bash
set -eu

REPO_URL="${1:-}"
BRANCH="${2:-main}"
TARGET_DIR="${3:-$HOME/Pesa-AI-Logger}"
SPARSE_PATH="phone_module/script"

if [ -z "$REPO_URL" ]; then
  echo "Usage: $0 <repo_url> [branch] [target_dir]"
  echo "Example: $0 git@github.com:you/Pesa-AI-Logger.git main \$HOME/Pesa-AI-Logger"
  exit 1
fi

if [ ! -d "$TARGET_DIR/.git" ]; then
  git clone --filter=blob:none --no-checkout "$REPO_URL" "$TARGET_DIR"
fi

git -C "$TARGET_DIR" sparse-checkout init --cone
git -C "$TARGET_DIR" sparse-checkout set "$SPARSE_PATH"
git -C "$TARGET_DIR" fetch --depth 1 origin "$BRANCH"
git -C "$TARGET_DIR" checkout -B "$BRANCH" "origin/$BRANCH"

SCRIPT_DIR="$TARGET_DIR/$SPARSE_PATH"
cd "$SCRIPT_DIR"

if [ ! -f config.json ]; then
  python mpesa_forwarder.py --init-config
fi

mkdir -p "$HOME/.termux/boot"
cp -f boot/start_forwarder.sh "$HOME/.termux/boot/start_forwarder.sh"
chmod +x "$HOME/.termux/boot/start_forwarder.sh" start.sh run_once.sh bootstrap_sparse_checkout.sh update_sparse_checkout.sh

echo "Sparse checkout ready at: $SCRIPT_DIR"
echo "Next:"
echo "  1) Edit config.json endpoint_url/api_key"
echo "  2) Run: python mpesa_forwarder.py --once --dry-run"
echo "  3) Start: ./start.sh"
