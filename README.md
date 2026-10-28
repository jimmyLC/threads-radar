# Threads 主題輿論雷達

每天抓一次 Threads 上特定關鍵字的公開討論，存進 SQLite，用一個極簡網頁看清單。
設計原則：單人使用、零維運動、月成本 < NT$1,000。

- 平台：**Threads**（官方 API）；Facebook 公開貼文沒有官方關鍵字 API，故不在系統內
- 頻率：每日 09:00（Asia/Taipei）批次抓取，另有網頁「立即抓取」按鈕
- 輸出：每組關鍵字最新 15 則＋熱門 TOP 5、每則一行 LLM 摘要
- 保留：365 天，逾期自動清除

## 架構

```
VPS (Hetzner, Ubuntu 24.04, Asia/Taipei)
├─ radar-web     FastAPI，綁 127.0.0.1:8000（systemd）
├─ radar-fetch   每日抓取（systemd timer）
├─ data/radar.db SQLite（WAL）
└─ cloudflared   Tunnel → localhost:8000（不開任何 inbound port）
        │
Cloudflare Access（Email OTP 登入）
        │
   threads.jimmy-tools.com
```

## 目錄

```
radar/            主程式
  config.py       設定（.env、yaml）
  db.py / schema.sql
  threads_client.py  Threads Graph API 客戶端
  fetch.py        每日抓取（CLI：python -m radar.fetch）
  summarizer.py   LLM 一行摘要（OpenAI 相容 API）
  auth.py         OAuth 取得 token（CLI：python -m radar.auth）
  refresh.py      每週 token 更新（CLI：python -m radar.refresh）
  demo.py         示範資料（CLI：python -m radar.demo）
  web/            網頁
config/           keywords.yaml / exclusions.yaml（改了下一輪生效）
deploy/           systemd、cloudflared 設定、install.sh
scripts/backup.sh SQLite 備份（選配）
```

## 本機開發

```bash
cd threads-radar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # 編輯填入 API keys

.venv/bin/python -m radar.demo  # 灌示範資料（不打真 API）
.venv/bin/python -m radar.web   # 開 http://localhost:8000
```

清除示範資料：`.venv/bin/python -m radar.demo --wipe`

## Meta / Threads API 申請（最長前置，先做）

1. 到 [developers.facebook.com](https://developers.facebook.com) 建 App → 加入「Threads」→ 連結你的 Threads 帳號
2. App 設定 → Threads → **Redirect URI** 填 `http://localhost:8899/callback`
3. 申請權限：`threads_basic`、`threads_keyword_search` 的 **Advanced Access**
4. 完成 **Business Verification**（需要公司登記資料）
5. App Review 用途說明範本：
   > 監測 Threads 公開貼文中與 AI 產業相關的討論，供內部研究使用。不轉售資料、不公開展示個別用戶內容。
6. 審查期間（開發模式）API 只回傳**自己的貼文**——管線照樣可以建置與測試
7. 審查通過後切換：
   ```bash
   sqlite3 data/radar.db "INSERT OR REPLACE INTO settings VALUES('mode','live')"
   ```

### 取得 token

```bash
.venv/bin/python -m radar.auth     # 開瀏覽器走 OAuth，token 自動存進 DB
```

- token 有效期 60 天；`deploy` 內建的 timer 每週自動跑 `python -m radar.refresh`
- 到期日查詢：`sqlite3 data/radar.db "SELECT * FROM settings WHERE key LIKE 'token%'"`

## 部署到 VPS

```bash
# 本機：把專案同步上去（不要帶 .venv / data / .env）
rsync -av --exclude .venv --exclude data --exclude .env --exclude .git \
  ./ root@VPS_IP:/opt/radar/

# VPS 上：
ssh root@VPS_IP
cd /opt/radar
cp .env.example .env && vim .env          # 填入 LLM key 等
bash deploy/install.sh                    # 裝依賴、註冊 systemd、裝 cloudflared
```

### Cloudflare Tunnel ＋ Access

```bash
cloudflared tunnel login                  # 瀏覽器授權
cloudflared tunnel create radar
cp deploy/cloudflared-config.example.yml ~/.cloudflared/config.yml
vim ~/.cloudflared/config.yml             # 換 tunnel id 與網域
cloudflared tunnel route dns radar threads.jimmy-tools.com
sudo cloudflared service install
```

Zero Trust 後台 → **Access → Applications → Add → Self-hosted**：
- Domain：`threads.jimmy-tools.com`
- Policy：Allow / Include / Emails = 你的信箱（登入方式選 One-time PIN）
- Session Duration：1 week

## 日常維運

```bash
# 看抓取 log
journalctl -u radar-fetch -f
journalctl -u radar-web -f

# 手動抓一輪
cd /opt/radar && .venv/bin/python -m radar.fetch

# 關鍵字管理：直接在網頁側欄「＋ 新增」／hover 按 ✕ 刪除（新增後立即搜尋一次）
# 進階：直接改資料庫
#   sqlite3 data/radar.db "INSERT INTO keywords(term) VALUES('NVIDIA')"
#   sqlite3 data/radar.db "DELETE FROM keywords WHERE term='NVIDIA'"
# config/keywords.yaml 僅在資料庫空白時當作初始種子，之後以資料庫為準

# 手動更新 token
.venv/bin/python -m radar.refresh

# 備份（選配）
bash scripts/backup.sh
```

健康檢查：`https://threads.jimmy-tools.com/health`（上次成功抓取超過 26 小時會回 503，可掛 UptimeRobot 免費監測）。

## Threads API 資料範圍

`keyword_search` 每則回傳：`id`、`text`（內文）、`username`、`permalink`、`timestamp`、`is_reply`／`has_replies`、`topic_tag`、`media_type`（TEXT/IMAGE/VIDEO）、`is_verified`。
搜尋方式：`search_type=RECENT|TOP`、`search_mode=KEYWORD|TAG`、可加 `author_username` 鎖定帳號、`since/until` 切時間窗。

**拿不到的**：讚／留言／分享／瀏覽數（只在自家帳號 Insights）、別人的回覆串（`/{id}/replies` 僅限自家貼文）、私密社團與 DM。
**硬限制**：2,200 次查詢／user／24h；`since` 最早 2023-07-05；敏感詞回空陣列；公開搜尋需 App Review＋商業驗證；中文召回 Meta 不保證。

## 已知限制（設計取捨，不是 bug）

1. **沒有互動數**：Threads API 不回傳讚／留言／分享。「熱門 TOP」是 Meta 的排序，不是最多讚。
2. **15 則是樣本**：用途是「今天大家在聊什麼」，不是聲量統計。
3. **中文召回未經 Meta 保證**：上線第一週拿幾則你知道的熱門 AI 貼文做召回測試，抓不到就調關鍵字。
4. **「AI」雜訊多**：課程、直銷、AI 繪圖會進來，排除詞要邊跑邊加（`config/exclusions.yaml`）。
5. **App Review 時間不可控**：管線先用開發模式建置，權限下來即切換。

## 成本

| 項目 | 月費 |
|---|---|
| Hetzner CX23 | ≈ US$7.7（≈ NT$250） |
| 網域攤提 | ≈ NT$25 |
| LLM 摘要 | ≈ NT$50–150 |
| Cloudflare（Tunnel＋Access 免費方案） | 0 |
| **合計** | **≈ NT$350–450** |
