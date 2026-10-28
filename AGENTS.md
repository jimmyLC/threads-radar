# AGENTS.md

Threads 關鍵字輿論雷達。FastAPI ＋ SQLite ＋ 官方 Threads API；VPS 上跑，經 Cloudflare Tunnel 對外為 `threads.jimmy-tools.com`。單人使用，UI 繁體中文。

## 指令

```bash
.venv/bin/python -m radar.web                 # 網頁（127.0.0.1:8000，WEB_PORT 可覆寫）
.venv/bin/python -m radar.fetch               # 每日批次抓取（讀 DB 的關鍵字）
.venv/bin/python -m radar.auth                # OAuth 取 token（需 .env APP_ID/SECRET 與 HTTPS redirect URI）
.venv/bin/python -m radar.refresh             # 延長 long-lived token
.venv/bin/python -m radar.demo [--wipe]       # 灌入／清除示範資料
.venv/bin/python tests/test_fetch_offline.py  # 離線整合測試（monkeypatch API，不動正式 DB）
```

環境建置見 README。`.env` 從 `.env.example` 複製；`.env`、`data/`、`logs/` 永不進版控。

## 架構與落點

- `radar/threads_client.py` — Graph API 封裝。`keyword_search` 只回 `id/text/username/permalink/timestamp/is_reply/topic_tag`；**沒有讚數、留言數、分享數**。
- `radar/fetch.py` — `_fetch_keyword`（單一關鍵字：RECENT 24h，不足 5 則放寬 72h，再加 TOP）→ `_store`（去重、只摘要新貼文、purge 365 天）。`run_fetch` 是每日批次；`fetch_new_keyword` 是網頁新增關鍵字時的同步抓取。
- `radar/web/app.py` — 所有路由與頁面組裝。`/privacy`、`/data-deletion` 同時有 `.html` 別名（供 Cloudflare Pages 版共用同一份檔案）。
- `radar/db.py` ＋ `radar/schema.sql` — 連線 helper、`settings`、`init()`。

## 不變條件（改動前確認沒有破壞）

1. **時間**：DB 一律存 UTC `YYYY-MM-DD HH:MM:SS`；顯示與「分日」才加 `TZ_OFFSET_HOURS`（預設 8）。
2. **關鍵字來源是 DB** 的 `keywords` 表；`config/keywords.yaml` 只在 `db.init()` 播種。每日抓取、側欄、新增／刪除都讀 DB。
3. **排除詞在 `config/exclusions.yaml`**，比對時忽略大小寫與空白（中文斷詞空格）。
4. **貼文去重**用 `posts.id`；`mentions` 主鍵 `(post_id, keyword_id)`，`is_top` 取 MAX。
5. **dev 模式**（`settings.mode='dev'`）下官方 API 只回自己的貼文；審查通過後改 `live`。
6. **`runs` 表**是抓取紀錄：`running` 超過 1 小時視為 stale；`/api/run` 靠它避免重複執行；每次抓取在 `finally` 寫回結果。
7. **示範資料**只存在於 demo 模式，id 前綴 `demo`，`--wipe` 可清。
8. **`/api/keywords` 同步執行**（一般 2–6 秒），回傳 `{added, new_posts, info, error}`；即使抓取失敗也回 200，前端依 `error` 提示。

## 慣例

- UI 文案、註解用繁體中文；識別名英文。
- 樣板在 `radar/web/templates/`，CSS 與 JS 內嵌 `base.html`；不引入前端框架或 CDN。
- 新端點直接加在 `app.py`；查詢沿用 `db.connect()`，不另開連線池。
- 測試用假 API（`F.keyword_search = fake`）＋暫存 `RADAR_DB`，絕不寫正式資料。
- Commit message 用英文一句話描述變更。

## 常見陷阱

- `uvicorn` 沒有 reload：改 Python 或模板後要重啟程序。
- 不要在 Jinja `{{ }}` 裡塞多行 SQL；查詢先在 Python 組好再傳入。
- 新增貼文欄位要同步四處：`schema.sql`、`_normalize_post`、`_store` 的 INSERT、`_card`。
- demo 模式的 `seed_keyword` 只在「真的新增關鍵字」時觸發，避免重複灌資料。
- `fetch_new_keyword` 的 run 記錄也要在例外路徑寫回，否則 UI 會卡在「執行中」。

## 指向

- 部署（VPS、Cloudflare Tunnel、Access）：README「部署到 VPS」
- Meta 申請、送審、token：README「Meta / Threads API 申請」
- 目前進度、決策紀錄、待辦：`PROGRESS.md`
