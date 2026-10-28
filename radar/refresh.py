"""延長 long-lived token：python -m radar.refresh（建議每週跑一次）"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db
from .threads_client import ThreadsError, refresh_long_lived


def main() -> int:
    db.init()
    with db.connect() as c:
        token = db.get_setting(c, "access_token", "")
    if not token:
        print("沒有可更新的 token，先執行 python -m radar.auth")
        return 1
    try:
        new_token, expires_in = refresh_long_lived(token)
    except ThreadsError as e:
        print(f"更新失敗：{e}")
        return 1
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).strftime("%Y-%m-%d %H:%M:%S")
        if expires_in
        else ""
    )
    with db.connect() as c:
        db.set_setting(c, "access_token", new_token)
        if expires_at:
            db.set_setting(c, "token_expires_at", expires_at)
    print(f"✅ token 已更新，到期：{expires_at or '未知'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
