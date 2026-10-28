"""Threads Graph API：keyword_search 與 token 處理

文件：https://developers.facebook.com/docs/threads/keyword-search
注意：搜尋公開貼文需要 threads_keyword_search 的進階權限（App Review + 商業驗證），
     未通過審查時只會回傳授權使用者自己的貼文。
"""
from __future__ import annotations

import time

import httpx

from .config import APP_ID, APP_SECRET, GRAPH_BASE, GRAPH_VERSION, REDIRECT_URI

FIELDS = "id,text,permalink,timestamp,username,is_reply,topic_tag"
RETRY_SLEEPS = (15, 45, 90)  # 429 / 5xx / 網路錯誤時的退避秒數


class ThreadsError(Exception):
    pass


class TokenInvalidError(ThreadsError):
    """Token 失效或未設定（Graph error code 190）"""


def graph_get(path: str, params: dict) -> dict:
    """GET 回 200 就回傳 JSON；429/5xx/網路錯誤退避重試；其他錯誤直接丟例外。"""
    url = f"{GRAPH_BASE}/{path}"
    last = None
    for attempt in range(len(RETRY_SLEEPS) + 1):
        try:
            resp = httpx.get(url, params=params, timeout=30)
        except httpx.HTTPError as e:
            last = f"network error: {e}"
        else:
            if resp.status_code == 200:
                return resp.json()
            body = resp.text[:300]
            code = None
            try:
                code = resp.json().get("error", {}).get("code")
            except Exception:
                pass
            if code == 190 or resp.status_code == 401:
                raise TokenInvalidError(body)
            if resp.status_code == 429 or code in (4, 17, 32):
                last = f"rate limited: {body}"
            elif resp.status_code >= 500:
                last = f"HTTP {resp.status_code}: {body}"
            else:
                raise ThreadsError(f"HTTP {resp.status_code}: {body}")
        if attempt < len(RETRY_SLEEPS):
            time.sleep(RETRY_SLEEPS[attempt])
    raise ThreadsError(f"重試 {len(RETRY_SLEEPS)} 次後仍失敗：{last}")


def keyword_search(
    token: str,
    q: str,
    search_type: str = "RECENT",
    since: int | None = None,
    limit: int = 25,
) -> list[dict]:
    """公開貼文關鍵字搜尋。search_type: RECENT（時間序）或 TOP（熱門）。"""
    params = {
        "q": q,
        "search_type": search_type,
        "search_mode": "KEYWORD",
        "limit": limit,
        "fields": FIELDS,
        "access_token": token,
    }
    if since is not None:
        params["since"] = int(since)
    data = graph_get(f"{GRAPH_VERSION}/keyword_search", params)
    return data.get("data", [])


def exchange_code(code: str) -> str:
    """OAuth code → 短期 token（約 1 小時）"""
    resp = httpx.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise ThreadsError(f"交換 token 失敗：{resp.text[:300]}")
    return resp.json()["access_token"]


def to_long_lived(short_token: str) -> tuple[str, int]:
    """短期 token → long-lived token（約 60 天），回傳 (token, 秒數)"""
    resp = httpx.get(
        f"{GRAPH_BASE}/access_token",
        params={"grant_type": "th_exchange_token", "client_secret": APP_SECRET, "access_token": short_token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ThreadsError(f"換發 long-lived token 失敗：{resp.text[:300]}")
    d = resp.json()
    return d["access_token"], int(d.get("expires_in", 0))


def refresh_long_lived(token: str) -> tuple[str, int]:
    """延長 long-lived token（每日最多一次，延長 60 天）"""
    resp = httpx.get(
        f"{GRAPH_BASE}/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ThreadsError(f"更新 token 失敗：{resp.text[:300]}")
    d = resp.json()
    return d["access_token"], int(d.get("expires_in", 0))


def me(token: str) -> dict:
    resp = httpx.get(
        f"{GRAPH_BASE}/{GRAPH_VERSION}/me",
        params={"fields": "id,username", "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ThreadsError(f"取得使用者資訊失敗：{resp.text[:300]}")
    return resp.json()
