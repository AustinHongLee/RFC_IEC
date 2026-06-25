#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "============================================"
echo "  焊口管理系統  Weld Joint Management System"
echo "============================================"

if [ ! -d ".venv" ]; then
  echo "第一次執行,建立虛擬環境並安裝套件..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

echo "啟動伺服器:http://127.0.0.1:8000"
python app.py
