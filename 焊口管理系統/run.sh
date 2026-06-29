#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "============================================"
echo "  焊口管理系統  Weld Joint Management System"
echo "============================================"

if [ ! -d ".venv" ]; then
  echo "第一次執行,建立虛擬環境..."
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import fastapi, uvicorn, openpyxl, multipart" 2>/dev/null; then
  echo "安裝套件中(約 1 分鐘)..."
  python -m pip install --disable-pip-version-check -r requirements.txt
fi

echo "啟動伺服器:http://127.0.0.1:8000"
python app.py
