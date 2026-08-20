#!/usr/bin/env bash
set -e

REPO_DIR="/Users/omar/Downloads/arabic-schoolbook-ocr"

cd "$REPO_DIR"

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# Record heartbeat update
echo "- Local activity check: $TIMESTAMP" >> HEARTBEAT.md

git add HEARTBEAT.md
git commit -m "chore: scheduled periodic update [$TIMESTAMP]" || exit 0
git push origin main
