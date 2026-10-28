"""網頁（單頁清單 + 手動抓取）。所有資料都在本機 SQLite，經 Cloudflare Access 對外。"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import db
from ..config import BASE_DIR, TZ_OFFSET_HOURS

SITE_DIR = Path(__file__).resolve().parent / "site"


class TermIn(BaseModel):
    term: str

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
STATUS_TEXT = {"ok": "成功", "running": "執行中", "partial": "部分成功", "failed": "失敗"}


def _tpe(s: str) -> str:
    """UTC 'YYYY-MM-DD HH:MM:SS' → 當地 'MM-DD HH:MM'"""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S") + timedelta(hours=TZ_OFFSET_HOURS)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return s


def _tpe_day(s: str) -> str:
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S") + timedelta(hours=TZ_OFFSET_HOURS)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return s


templates.env.filters["tpe"] = _tpe
templates.env.filters["tpe_day"] = _tpe_day


def _today_str() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%d")


def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _esc_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _card(row) -> dict:
    d = dict(row)
    d["time_str"] = _tpe(d["posted_at"])
    return d


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="Threads 輿論雷達", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy.html", response_class=HTMLResponse)
async def privacy_page():
    """隱私政策（Meta 發佈／審查要求項目）"""
    return FileResponse(SITE_DIR / "privacy.html", media_type="text/html")


@app.get("/data-deletion", response_class=HTMLResponse)
@app.get("/data-deletion.html", response_class=HTMLResponse)
async def data_deletion_page():
    """資料刪除說明（Meta 發佈／審查要求項目）"""
    return FileResponse(SITE_DIR / "data-deletion.html", media_type="text/html")


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    keyword: str | None = None,
    date: str | None = None,
    q: str | None = None,
    show_all: int = Query(0, alias="all"),
):
    today = _today_str()
    d = date if (date and _valid_date(date)) else today
    day_expr = f"date(datetime(p.posted_at, '+{TZ_OFFSET_HOURS} hours'))"

    with db.connect() as c:
        krows = c.execute("SELECT id, term FROM keywords ORDER BY id").fetchall()
        counts = {
            r["term"]: r["n"]
            for r in c.execute(
                f"""
                SELECT k.term, COUNT(DISTINCT p.id) AS n
                FROM keywords k
                LEFT JOIN mentions m ON m.keyword_id = k.id
                LEFT JOIN posts p ON p.id = m.post_id AND {day_expr} = ?
                GROUP BY k.id ORDER BY k.id
                """,
                (d,),
            )
        }
        all_count = c.execute(
            f"SELECT COUNT(DISTINCT p.id) AS n FROM posts p "
            f"WHERE {day_expr} = ? AND EXISTS(SELECT 1 FROM mentions m WHERE m.post_id = p.id)",
            (d,),
        ).fetchone()["n"]
        last_row = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        mode = db.get_setting(c, "mode", "dev")
        demo = db.get_setting(c, "demo", "0") == "1"

        posts, top_posts, total = [], [], 0
        kid = None
        if keyword and not q:
            krow = c.execute("SELECT id FROM keywords WHERE term=?", (keyword,)).fetchone()
            kid = krow["id"] if krow else -1

        if q:
            like = f"%{_esc_like(q)}%"
            rows = c.execute(
                "SELECT * FROM posts WHERE text LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
                "ORDER BY posted_at DESC LIMIT 50",
                (like, like),
            ).fetchall()
            posts = [_card(r) for r in rows]
            total = len(posts)
        else:
            limit = 1000 if show_all else 15
            if kid is not None:
                total = c.execute(
                    f"SELECT COUNT(DISTINCT p.id) AS n FROM posts p JOIN mentions m ON m.post_id=p.id "
                    f"WHERE m.keyword_id = ? AND {day_expr} = ?",
                    (kid, d),
                ).fetchone()["n"]
                top_rows = c.execute(
                    f"SELECT p.*, 1 AS is_top FROM posts p JOIN mentions m ON m.post_id=p.id AND m.is_top=1 "
                    f"WHERE m.keyword_id = ? AND {day_expr} = ? "
                    f"GROUP BY p.id ORDER BY p.posted_at DESC LIMIT 5",
                    (kid, d),
                ).fetchall()
                rows = c.execute(
                    f"SELECT p.*, MAX(m.is_top) AS is_top FROM posts p JOIN mentions m ON m.post_id=p.id "
                    f"WHERE m.keyword_id = ? AND {day_expr} = ? "
                    f"AND p.id NOT IN (SELECT m2.post_id FROM mentions m2 WHERE m2.keyword_id = ? AND m2.is_top = 1) "
                    f"GROUP BY p.id ORDER BY p.posted_at DESC LIMIT ?",
                    (kid, d, kid, limit),
                ).fetchall()
            else:
                total = all_count  # 「全部關鍵字」的總數就是側欄的全域計數
                top_rows = c.execute(
                    f"SELECT p.*, 1 AS is_top FROM posts p JOIN mentions m ON m.post_id=p.id AND m.is_top=1 "
                    f"WHERE {day_expr} = ? GROUP BY p.id ORDER BY p.posted_at DESC LIMIT 5",
                    (d,),
                ).fetchall()
                rows = c.execute(
                    f"SELECT p.* FROM posts p WHERE {day_expr} = ? "
                    f"AND EXISTS(SELECT 1 FROM mentions m WHERE m.post_id = p.id) "
                    f"AND p.id NOT IN (SELECT post_id FROM mentions WHERE is_top = 1) "
                    f"ORDER BY p.posted_at DESC LIMIT ?",
                    (d, limit),
                ).fetchall()
            top_posts = [_card(r) for r in top_rows]
            posts = [_card(r) for r in rows]

    last_run = None
    if last_row:
        lr = dict(last_row)
        last_run = {
            "status": lr["status"],
            "text": STATUS_TEXT.get(lr["status"], lr["status"]),
            "time_str": _tpe(lr["finished_at"] or lr["started_at"]),
        }

    params = {"keyword": keyword} if keyword else {}
    prev_qs = urllib.parse.urlencode({**params, "date": _shift_day(d, -1)})
    next_qs = urllib.parse.urlencode({**params, "date": _shift_day(d, 1)})

    # 最近 7 天的快捷連結（今天／昨天／前天／MM-DD…）
    base = datetime.strptime(today, "%Y-%m-%d")
    rel = {0: "今天", 1: "昨天", 2: "前天"}
    days = []
    for i in range(7):
        day_dt = base - timedelta(days=i)
        ds = day_dt.strftime("%Y-%m-%d")
        days.append({
            "ds": ds,
            "label": rel.get(i, day_dt.strftime("%m-%d")),
            "qs": urllib.parse.urlencode({**params, "date": ds}),
        })

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "keywords": [{"term": r["term"], "n": counts.get(r["term"], 0)} for r in krows],
            "all_count": all_count,
            "keyword": keyword,
            "d": d,
            "today": today,
            "q": q,
            "posts": posts,
            "top_posts": top_posts,
            "total": total,
            "show_all": show_all,
            "prev_qs": prev_qs,
            "next_qs": next_qs,
            "days": days,
            "last_run": last_run,
            "mode": mode,
            "demo": demo,
        },
    )


def _shift_day(day: str, delta: int) -> str:
    dt = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=delta)
    return dt.strftime("%Y-%m-%d")


@app.post("/api/run")
async def api_run():
    with db.connect() as c:
        stale = c.execute(
            "SELECT id FROM runs WHERE status='running' AND started_at < datetime('now','-1 hour')"
        ).fetchall()
        for r in stale:
            c.execute(
                "UPDATE runs SET status='failed', finished_at=?, detail=? WHERE id=?",
                (db.utcnow_str(), json.dumps({"error": "stale"}), r["id"]),
            )
        if c.execute("SELECT COUNT(*) AS n FROM runs WHERE status='running'").fetchone()["n"]:
            return JSONResponse({"error": "run_already_active"}, status_code=409)
    subprocess.Popen(
        [sys.executable, "-m", "radar.fetch"],
        cwd=str(BASE_DIR),
        start_new_session=True,
    )
    return {"status": "started"}


@app.get("/api/runs/latest")
async def api_runs_latest():
    with db.connect() as c:
        row = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"status": "no_runs"}
    d = dict(row)
    try:
        d["detail"] = json.loads(d["detail"] or "{}")
    except Exception:
        d["detail"] = {}
    return d


@app.post("/api/keywords")
def api_keywords_add(body: TermIn):
    """新增關鍵字並立即抓一輪（同步執行，一般 2–6 秒）。"""
    term = (body.term or "").strip()
    if not term:
        return JSONResponse({"error": "關鍵字不可空白"}, status_code=400)
    from ..fetch import fetch_new_keyword

    return fetch_new_keyword(term)


@app.post("/api/keywords/delete")
def api_keywords_delete(body: TermIn):
    term = (body.term or "").strip()
    if not term:
        return JSONResponse({"error": "關鍵字不可空白"}, status_code=400)
    with db.connect() as c:
        c.execute("DELETE FROM keywords WHERE LOWER(term)=LOWER(?)", (term,))
    return {"status": "deleted", "term": term}


@app.get("/health")
async def health():
    with db.connect() as c:
        last_ok = c.execute("SELECT MAX(finished_at) AS t FROM runs WHERE status='ok'").fetchone()["t"]
    if not last_ok:
        return {"status": "no_runs_yet"}
    last = datetime.strptime(last_ok, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last > timedelta(hours=26):
        return JSONResponse({"status": "stale", "last_ok": last_ok}, status_code=503)
    return {"status": "ok", "last_ok": last_ok}
