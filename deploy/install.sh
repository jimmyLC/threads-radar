#!/usr/bin/env bash
# 在 VPS（Ubuntu 24.04, root）上執行。專案需已放在 /opt/radar
set -euo pipefail

APP_DIR=/opt/radar

echo "== 系統依賴 =="
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip sqlite3 curl >/dev/null
timedatectl set-timezone Asia/Taipei || true

echo "== Python 環境 =="
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== 資料與設定 =="
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"
[ -f "$APP_DIR/.env" ] || { cp "$APP_DIR/.env.example" "$APP_DIR/.env"; echo "  ⚠️ 請編輯 $APP_DIR/.env 填入 API keys"; }

echo "== systemd =="
cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now radar-web.service
systemctl enable --now radar-fetch.timer
systemctl enable --now radar-refresh.timer

echo "== cloudflared =="
if [ ! -x /usr/local/bin/cloudflared ]; then
  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
fi

echo
echo "✅ 安裝完成。剩餘手動步驟："
echo "  1. cloudflared tunnel login"
echo "  2. cloudflared tunnel create radar"
echo "  3. cp deploy/cloudflared-config.example.yml ~/.cloudflared/config.yml（換 tunnel id）"
echo "  4. cloudflared tunnel route dns radar threads.jimmy-tools.com"
echo "  5. sudo cloudflared service install"
echo "  6. Cloudflare Zero Trust → Access → 加入 threads.jimmy-tools.com 與你的信箱"
echo "  7. .venv/bin/python -m radar.auth 取得 token（SSH -L 8899:localhost:8899）"
