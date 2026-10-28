"""啟動網頁：python -m radar.web（可用 WEB_HOST / WEB_PORT 覆寫）"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "radar.web.app:app",
        host=os.getenv("WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("WEB_PORT", "8000")),
        log_level="info",
    )
