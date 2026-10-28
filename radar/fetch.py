"""抓取：每日批次（python -m radar.fetch）與新增關鍵字後的即時搜尋

共用流程：RECENT 24h（不足 5 則放寬 72h）＋ TOP ＋ 排除詞過濾 ＋ 去重寫入。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

from . import db
from .config import RETENTION_DAYS, load_exclusions
from .threads_client import ThreadsError, TokenInvalidError, keyword_search


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def _excluded(text: str, exclusions: list[str]) -> bool:
    t = text.lower()
    tc = t.replace(" ", "").replace("\u3000", "")  # 中文句常有空格斷詞，比對時去掉
    return any(x in t or x in tc for x in exclusions)


def _normalize_post(raw: dict) -> dict:
    ts = raw.get("timestamp") or ""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        dt = datetime.now(timezone.utc)
    return {
        "id": str(raw["id"]),
        "author": raw.get("username") or "unknown",
        "text": raw.get("text") or "",
        "permalink": raw.get("permalink") or "",
        "posted_at": dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "is_reply": 1 if raw.get("is_reply") else 0,
        "topic_tag": raw.get("topic_tag"),
    }


def _fetch_keyword(token: str, term: str, kid: int, exclusions: list[str], now: datetime | None = None):
    """抓單一關鍵字。回傳 (info, {post_id: post}, {(post_id, kid): mention})"""
    now = now or datetime.now(timezone.utc)
    info: dict = {"recent": 0, "top": 0, "window": 24, "error": None}
    posts_out: dict[str, dict] = {}
    mentions_out: dict[tuple[str, int], dict] = {}

    # 最新（RECENT）：24 小時不夠就放寬到 72
    kept: list[dict] = []
    window = 24
    for hrs in (24, 72):
        since = _epoch(now - timedelta(hours=hrs))
        raw = keyword_search(token, term, "RECENT", since=since, limit=25)
        kept = [p for p in raw if not _excluded(p.get("text") or "", exclusions)]
        window = hrs
        if len(kept) >= 5:
            break
    info["recent"] = len(kept)
    info["window"] = window

    # 熱門（TOP）
    top_raw = keyword_search(token, term, "TOP", since=_epoch(now - timedelta(hours=24)), limit=5)
    if not top_raw:
        top_raw = keyword_search(token, term, "TOP", since=_epoch(now - timedelta(hours=72)), limit=5)
    top_kept = [p for p in top_raw if not _excluded(p.get("text") or "", exclusions)]
    info["top"] = len(top_kept)
    top_ids = {p["id"] for p in top_kept}

    for p in kept + top_kept:
        norm = _normalize_post(p)
        pid = norm["id"]
        posts_out[pid] = norm
        m = mentions_out.setdefault((pid, kid), {"is_top": 0, "window": window})
        if pid in top_ids:
            m["is_top"] = 1
    return info, posts_out, mentions_out


def _store(posts_by_id: dict[str, dict], mention_map: dict) -> int:
    """寫入貼文與提及；只對 DB 沒有的新貼文做 LLM 摘要。回傳新貼文數。"""
    with db.connect() as c:
        existing: set[str] = set()
        ids = list(posts_by_id)
        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            marks = ",".join("?" * len(chunk))
            for r in c.execute(f"SELECT id FROM posts WHERE id IN ({marks})", chunk):
                existing.add(r["id"])
    new_posts = [p for pid, p in posts_by_id.items() if pid not in existing]

    summaries: dict[str, str] = {}
    if new_posts:
        try:
            from .summarizer import summarize

            summaries = summarize(new_posts)
        except Exception as e:  # 摘要失敗不影響抓取
            print(f"[fetch] 摘要失敗（略過）：{e!r}", flush=True)

    with db.connect() as c:
        for p in new_posts:
            c.execute(
                "INSERT INTO posts(id, author, text, permalink, posted_at, is_reply, topic_tag, summary, first_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    p["id"],
                    p["author"],
                    p["text"],
                    p["permalink"],
                    p["posted_at"],
                    p["is_reply"],
                    p["topic_tag"],
                    summaries.get(p["id"]),
                    db.utcnow_str(),
                ),
            )
        for (pid, kid), m in mention_map.items():
            c.execute(
                "INSERT INTO mentions(post_id, keyword_id, is_top, window_hours, seen_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(post_id, keyword_id) DO UPDATE SET "
                "is_top=MAX(mentions.is_top, excluded.is_top), seen_at=excluded.seen_at",
                (pid, kid, m["is_top"], m["window"], db.utcnow_str()),
            )
        c.execute(
            "DELETE FROM posts WHERE posted_at < datetime('now', ?)",
            (f"-{RETENTION_DAYS} days",),
        )
    return len(new_posts)


def run_fetch() -> int:
    db.init()
    run_id = None
    status = "ok"
    detail: dict = {}
    try:
        # 清掉卡住的舊 run（例如機器在抓取中重開機）
        with db.connect() as c:
            c.execute(
                "UPDATE runs SET status='failed', finished_at=?, detail=? "
                "WHERE status='running' AND started_at < datetime('now','-1 hour')",
                (db.utcnow_str(), json.dumps({"error": "stale"})),
            )
            if c.execute("SELECT COUNT(*) AS n FROM runs WHERE status='running'").fetchone()["n"]:
                print("[fetch] 已有抓取進行中，跳過", flush=True)
                return 0
            run_id = c.execute(
                "INSERT INTO runs(started_at, status) VALUES(?, 'running')", (db.utcnow_str(),)
            ).lastrowid
            token = db.get_setting(c, "access_token") or os.getenv("THREADS_ACCESS_TOKEN", "")
            kw_rows = c.execute("SELECT id, term FROM keywords WHERE enabled=1 ORDER BY id").fetchall()

        if not token:
            raise TokenInvalidError("尚未設定 access_token，先執行 python -m radar.auth")

        exclusions = [e.lower() for e in load_exclusions()]
        now = datetime.now(timezone.utc)
        posts_by_id: dict[str, dict] = {}
        mention_map: dict[tuple[str, int], dict] = {}

        for krow in kw_rows:
            kid, term = krow["id"], krow["term"]
            try:
                info, p_out, m_out = _fetch_keyword(token, term, kid, exclusions, now=now)
                detail[term] = info
                posts_by_id.update(p_out)
                for key, m in m_out.items():
                    cur = mention_map.setdefault(key, m)
                    cur["is_top"] = max(cur["is_top"], m["is_top"])
            except TokenInvalidError:
                detail[term] = {"error": "token_invalid"}
                status = "failed"
                break
            except ThreadsError as e:
                detail[term] = {"error": str(e)}
                status = "partial"
            print(
                f"[fetch] {term}: recent={detail[term].get('recent', 0)} top={detail[term].get('top', 0)} "
                f"window={detail[term].get('window', '?')}h err={detail[term].get('error')}",
                flush=True,
            )

        n_new = _store(posts_by_id, mention_map)
        print(f"[fetch] 完成：新貼文 {n_new} 則、提及 {len(mention_map)} 筆、狀態 {status}", flush=True)
    except TokenInvalidError as e:
        status = "failed"
        detail["fatal"] = str(e)
        print(f"[fetch] Token 無效：{e}", flush=True)
    except Exception as e:
        status = "failed"
        detail["fatal"] = repr(e)
        print(f"[fetch] 未預期錯誤：{e!r}", flush=True)
    finally:
        if run_id is not None:
            with db.connect() as c:
                c.execute(
                    "UPDATE runs SET status=?, finished_at=?, detail=? WHERE id=?",
                    (status, db.utcnow_str(), json.dumps(detail, ensure_ascii=False), run_id),
                )
    return 0 if status == "ok" else 1


def fetch_new_keyword(term: str) -> dict:
    """新增關鍵字並立即抓一輪。網頁「新增關鍵字」呼叫。"""
    db.init()
    term = (term or "").strip()[:60]
    out: dict = {"term": term, "added": False, "new_posts": 0, "info": None, "error": None}
    if not term:
        out["error"] = "關鍵字不可空白"
        return out

    with db.connect() as c:
        row = c.execute("SELECT id FROM keywords WHERE LOWER(term)=LOWER(?)", (term,)).fetchone()
        if row:
            kid = row["id"]
        else:
            kid = c.execute("INSERT INTO keywords(term) VALUES(?)", (term,)).lastrowid
            out["added"] = True
        token = db.get_setting(c, "access_token") or os.getenv("THREADS_ACCESS_TOKEN", "")
        is_demo = db.get_setting(c, "demo", "0") == "1"

    # 示範模式：真的新增時灌幾則該關鍵字的假貼文，讓 UI 體驗完整
    if is_demo and not token:
        if out["added"]:
            from .demo import seed_keyword

            out["new_posts"] = seed_keyword(term, kid)
        return out

    if not token:
        out["error"] = "尚未設定 access_token（python -m radar.auth）。關鍵字已加入，權限生效後每日抓取會自動涵蓋。"
        return out

    with db.connect() as c:
        run_id = c.execute(
            "INSERT INTO runs(started_at, status) VALUES(?, 'running')", (db.utcnow_str(),)
        ).lastrowid
    status = "ok"
    try:
        exclusions = [e.lower() for e in load_exclusions()]
        info, posts_by_id, mention_map = _fetch_keyword(token, term, kid, exclusions)
        out["info"] = info
        out["new_posts"] = _store(posts_by_id, mention_map)
        if info["error"]:
            out["error"] = info["error"]
            status = "partial"
        print(
            f"[fetch] 即時搜尋 {term}: recent={info['recent']} top={info['top']} 新增={out['new_posts']}",
            flush=True,
        )
    except TokenInvalidError as e:
        out["error"] = f"token 無效：{e}"
        status = "failed"
    except ThreadsError as e:
        out["error"] = str(e)
        status = "failed"
    finally:
        with db.connect() as c:
            c.execute(
                "UPDATE runs SET status=?, finished_at=?, detail=? WHERE id=?",
                (
                    status,
                    db.utcnow_str(),
                    json.dumps({term: out["info"] or {"error": out["error"]}}, ensure_ascii=False),
                    run_id,
                ),
            )
    return out


if __name__ == "__main__":
    sys.exit(run_fetch())
