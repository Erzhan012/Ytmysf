#!/usr/bin/env bash
set -euo pipefail
# Simple local runner
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

mkdir -p "${TEMP_DIR:-/tmp/telegram_music_bot}"
python main.py
