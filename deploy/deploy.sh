#!/usr/bin/env bash
# Deploy on VPS: pull latest main and restart. Run from /opt/rumis-bot.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> git pull"
git fetch origin
git pull --ff-only origin main

echo "==> deps"
./.venv/bin/pip install -q -r requirements.txt

echo "==> restart"
systemctl restart rumis-bot
sleep 2
systemctl is-active rumis-bot
journalctl -u rumis-bot -n 15 --no-pager
echo "==> done"
