"""OAuth 取得 long-lived token：python -m radar.auth

需要先在 .env 設定 THREADS_APP_ID / THREADS_APP_SECRET，
並在 Meta App 後台把 Redirect URI 設為 .env 裡的 THREADS_REDIRECT_URI。
VPS 上沒有瀏覽器時，用 SSH 轉埠：ssh -L 8899:localhost:8899 vps
"""
from __future__ import annotations

import threading
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import db
from .config import APP_ID, APP_SECRET, REDIRECT_URI
from .threads_client import ThreadsError, exchange_code, me, to_long_lived

AUTH_URL = "https://threads.com/oauth/authorize"
SCOPE = "threads_basic,threads_keyword_search"


def main() -> int:
    db.init()
    if not (APP_ID and APP_SECRET):
        print("請先在 .env 設定 THREADS_APP_ID / THREADS_APP_SECRET")
        return 1

    port = urllib.parse.urlparse(REDIRECT_URI).port or 8899
    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = (q.get("code") or [None])[0]
            err = (q.get("error_description") or q.get("error") or [None])[0]
            if not code and not err:
                # 不是 OAuth 回呼（隧道健康檢查、誤觸），保持等待
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<meta charset='utf-8'><body style='font-family:sans-serif'>⏳ 等待授權回呼…</body>".encode())
                return
            result["code"] = code
            result["error"] = err
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "✅ 授權完成，請回到終端機。" if code else "❌ 授權被拒絕或失敗，請回到終端機看訊息。"
            self.wfile.write(f"<meta charset='utf-8'><body style='font-family:sans-serif'>{msg}</body>".encode())
            done.set()

        def log_message(self, *args):
            pass

    params = urllib.parse.urlencode(
        {"client_id": APP_ID, "redirect_uri": REDIRECT_URI, "scope": SCOPE, "response_type": "code"}
    )
    print(f"如瀏覽器沒有自動開啟，請手動打開：\n{AUTH_URL}?{params}\n")
    try:
        webbrowser.open(f"{AUTH_URL}?{params}")
    except Exception:
        pass

    server = HTTPServer(("localhost", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not done.wait(timeout=600):
        print("逾時：10 分鐘內未收到授權回呼")
        return 1
    server.shutdown()

    if result.get("error") or not result.get("code"):
        print(f"授權失敗：{result.get('error')}")
        return 1
    try:
        short = exchange_code(result["code"])
        token, expires_in = to_long_lived(short)
        user = me(token)
    except ThreadsError as e:
        print(f"失敗：{e}")
        return 1

    expires_at = (
        (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).strftime("%Y-%m-%d %H:%M:%S")
        if expires_in
        else ""
    )
    with db.connect() as c:
        db.set_setting(c, "access_token", token)
        if expires_at:
            db.set_setting(c, "token_expires_at", expires_at)
        db.set_setting(c, "threads_user_id", user.get("id", ""))
        db.set_setting(c, "threads_username", user.get("username", ""))
    print(f"✅ 已存入 long-lived token（@{user.get('username', '?')}）到期：{expires_at or '未知'}")
    print("審查通過後記得切換：sqlite3 data/radar.db \"INSERT OR REPLACE INTO settings VALUES('mode','live')\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
