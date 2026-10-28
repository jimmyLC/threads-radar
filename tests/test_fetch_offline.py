"""離線整合測試：monkeypatch keyword_search，驗證抓取→過濾→去重→入庫全流程。

執行：.venv/bin/python tests/test_fetch_offline.py
使用獨立的暫存 DB，不會動到正式資料。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tmp = Path(tempfile.mkdtemp())
os.environ["RADAR_DB"] = str(tmp / "test.db")

import radar.fetch as F  # noqa: E402  (env 已設好才 import)
from radar import db  # noqa: E402

NOW = datetime.now(timezone.utc)


def ts(h: float) -> str:
    return (NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S+0000")


FIXTURES: dict[str, dict] = {}


def set_kw(term: str, recent: list[dict], top: list[dict]):
    FIXTURES[term.lower()] = {"RECENT": recent, "TOP": top}


def fake_keyword_search(token, q, search_type="RECENT", since=None, limit=25):
    data = FIXTURES.get(q.lower())
    assert data is not None, f"unexpected query: {q}"
    return data[search_type]


# ---- 佈置測資 ----
# AI：3 則正常 + 1 則命中排除詞；TOP 回 1 則（與 RECENT 重疊，測 is_top 合併）
set_kw(
    "AI",
    recent=[
        {"id": "t1", "text": "AI 代理开始在生产线排障", "username": "u1", "permalink": "p1", "timestamp": ts(1), "is_reply": False},
        {"id": "t2", "text": "AI 檔 太大轉不了 PDF，問一下大家", "username": "u2", "permalink": "p2", "timestamp": ts(2), "is_reply": False},
        {"id": "t3", "text": "The AI race is heating up", "username": "u3", "permalink": "p3", "timestamp": ts(3), "is_reply": True},
    ],
    top=[
        {"id": "t1", "text": "AI 代理开始在生产线排障", "username": "u1", "permalink": "p1", "timestamp": ts(1), "is_reply": False},
    ],
)
# OpenAI：RECENT 0 則 → 觸發 72h 放寬（72h 仍 0）；TOP 72h 回 1 則
set_kw("OpenAI", recent=[], top=[{"id": "t9", "text": "OpenAI 週年回顧", "username": "u9", "permalink": "p9", "timestamp": ts(60), "is_reply": False}])
set_kw("ChatGPT", recent=[{"id": "t4", "text": "ChatGPT 又改版了", "username": "u4", "permalink": "p4", "timestamp": ts(4), "is_reply": False}], top=[])
# 大型語言模型：24h 2 則（<5 → 72h 放寬，合併後 3 則）
old = [{"id": f"t5{i}", "text": f"大型語言模型 考古 {i}", "username": "u5", "permalink": f"p5{i}", "timestamp": ts(40 + i), "is_reply": False} for i in range(2)]
set_kw(
    "大型語言模型",
    recent=[{"id": "t5x", "text": "大型語言模型 新玩意", "username": "u5", "permalink": "p5x", "timestamp": ts(2), "is_reply": False}] + old,
    top=[],
)

F.keyword_search = fake_keyword_search

# 只留 4 個關鍵字，其他關掉；塞一個假 token（fake API 不會真的驗）
db.init()
with db.connect() as c:
    c.execute("UPDATE keywords SET enabled = CASE WHEN term IN ('AI','OpenAI','ChatGPT','大型語言模型') THEN 1 ELSE 0 END")
    db.set_setting(c, "access_token", "TEST_TOKEN")

rc = F.run_fetch()
assert rc == 0, f"run_fetch 應成功，rc={rc}"

with db.connect() as c:
    posts = {r["id"]: r for r in c.execute("SELECT * FROM posts")}
    mentions = {(r["post_id"], r["keyword_id"]): r for r in c.execute("SELECT * FROM mentions")}
    run = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    terms = {r["term"]: r["id"] for r in c.execute("SELECT id, term FROM keywords")}

    def mget(pid, kid, col):
        r = mentions.get((pid, kid))
        return r[col] if r else None

    checks = []
    # 1. 排除詞生效：t2 不入庫
    checks.append(("排除詞擋掉 t2", "t2" not in posts))
    # 2. 去重與 is_top 合併：t1 在庫，且 (t1, AI) is_top=1
    checks.append(("t1 入庫", "t1" in posts))
    checks.append(("t1 標記熱門", mget("t1", terms["AI"], "is_top") == 1))
    # 3. TOP-only 貼文也入庫（t9）
    checks.append(("TOP-only t9 入庫", "t9" in posts))
    checks.append(("t9 標記熱門", mget("t9", terms["OpenAI"], "is_top") == 1))
    # 4. 72h 放寬有記錄
    checks.append(("OpenAI 用了 72h 窗", mget("t9", terms["OpenAI"], "window_hours") == 72))
    checks.append(("大型語言模型 用了 72h 窗", mget("t5x", terms["大型語言模型"], "window_hours") == 72))
    # 5. 老貼文（40h+）也在（放寬後抓到）
    checks.append(("老貼文 t50 入庫", "t50" in posts))
    # 6. 回覆標記
    checks.append(("t3 標記回覆", posts["t3"]["is_reply"] == 1))
    # 7. run 狀態
    checks.append(("run status=ok", run["status"] == "ok"))
    # 8. 未設定 LLM → summary 為空
    checks.append(("無 LLM 時 summary 空", posts["t1"]["summary"] is None))

ok = True
for name, passed in checks:
    print(("✅" if passed else "❌"), name)
    ok = ok and passed

# 9. 二輪抓取不重複摘要、不爆量
rc2 = F.run_fetch()
with db.connect() as c:
    n = c.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"]
checks.append(("二輪後貼文數不變", n == 7))
print(("✅" if n == 7 else "❌"), f"二輪後貼文數不變（n={n}）")
ok = ok and n == 7

print("\n結果：", "全部通過 ✅" if ok else "有失敗 ❌")
sys.exit(0 if ok else 1)
