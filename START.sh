#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PY="$VENV/bin/python"

echo
echo "=== Xiaomi Unlock Community Helper - Multi Offset ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] python3 belum terpasang."
    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "[!] python3-venv belum tersedia."
    sudo apt update
    sudo apt install -y python3-venv
fi

if [[ ! -d "$VENV" ]]; then
    echo "[i] Membuat virtual environment..."
    python3 -m venv "$VENV"
fi

if ! "$PY" - <<'PYTEST' >/dev/null 2>&1
import browser_cookie3, ntplib, pytz, urllib3, colorama
PYTEST
then
    echo "[i] Menginstal dependency Python..."
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install browser-cookie3 ntplib pytz urllib3 colorama
fi

exec "$PY" "$DIR/xiaomi_unlock_multi.py" "$@"
