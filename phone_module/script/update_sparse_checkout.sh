#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BRANCH="${1:-}"
SPARSE_PATH="phone_module/script"

if [ -z "$BRANCH" ]; then
  BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  if [ "$BRANCH" = "HEAD" ]; then
    BRANCH="main"
  fi
fi

git -C "$REPO_ROOT" sparse-checkout init --cone
git -C "$REPO_ROOT" sparse-checkout set "$SPARSE_PATH"
git -C "$REPO_ROOT" fetch origin "$BRANCH"
git -C "$REPO_ROOT" checkout "$BRANCH"
git -C "$REPO_ROOT" pull --ff-only origin "$BRANCH"

echo "Updated sparse checkout path: $SPARSE_PATH"
echo "Current commit: $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
