# PROGRESS.md

更新：2026-10-28

## 一句話狀態

功能已完成並在本機實測通過；**卡在 Meta 商家驗證 → App Review**；VPS 尚未部署（等 IP 與 SSH）。

## 已完成

- **抓取管線**：真實 API 驗證 28 次呼叫、0 錯誤（dev 模式 0 結果符合預期）；RECENT 24h→72h 放寬、TOP、排除詞、去重、365 天 purge
- **Token**：long-lived token（@jimmyon101），到期 2026-12-19；每週 refresh timer 已備（部署後生效）
- **網頁**：清單、日期快捷（今天／昨天／前天／MM-DD）、關鍵字新增＋即時搜尋、刪除、熱門 TOP、全文搜尋、立即抓取、失敗狀態顯示
- **修正**：TOP 與「最新」重複顯示；「全部」視窗總數為 0
- **法務頁**：隱私政策、資料刪除說明（contact@jimmy-tools.com），`/privacy`、`/data-deletion` 與 `.html` 別名
- **資產**：App 圖示 1024×1024（`deploy/app-icon.png`）
- **測試**：離線整合測試 12 項全過
- **Repo**：https://github.com/jimmyLC/threads-radar（public, MIT）

## 進行中／等待

- [ ] **Meta 商家驗證**（使用者操作中）→ 通過後才能申請 `threads_keyword_search` 進階權限
- [ ] Cloudflare Pages 上傳 `cloudflare-pages/` → 取得隱私政策 URL 填入 Meta
- [ ] VPS 部署（等 IP＋SSH 確認）
- [ ] Cloudflare Tunnel → `threads.jimmy-tools.com`
- [ ] Cloudflare Access：Allow 指定 email（One-time PIN）
- [ ] 送審：發佈 → 準備並提交應用程式審查 → 發佈
- [ ] 通過後切 live：`sqlite3 data/radar.db "INSERT OR REPLACE INTO settings VALUES('mode','live')"`

## 決策紀錄

| 題目 | 決定 | 理由 |
|---|---|---|
| 平台 | Threads 官方 API | FB 無公開關鍵字 API；非官方 Threads 爬蟲 2023 年全數被 Meta 停止 |
| FB（若需要） | Apify FB Search Scraper（約 US$19/月）或台灣廠商 KEYPO／i-Buzz | 自建不可能；Apify 最便宜且能接現有管線 |
| 架構 | VPS ＋ SQLite ＋ Cloudflare Tunnel ＋ Access | 不開 inbound port、零憑證管理；Pages 只放靜態法律頁 |
| 資料 | 保留 365 天；只存公開貼文文字／連結／帳號 | 避開個資與引用爭議 |
| 呈現 | 每組最新 15 則 ＋ TOP 5；不做情緒標記 | 純清單誤導風險低；情緒模型之後再加 |
| 節奏 | 每日 09:00 批次 ＋ 手動按鈕 | 24h 內 26 次查詢，遠低於 2,200/日上限 |
| 預算 | < NT$1,000/月 | Hetzner ≈250、LLM 摘要 50–150、Cloudflare 0 |

## 已知風險

- **中文召回未驗證**：Meta 不保證 CJK 斷詞；上線第一週拿 3 則已知熱門貼文做召回測試
- **「AI」雜訊高**：課程、直銷、AI 繪圖會進來；排除詞需持續調整
- **無互動數**：TOP 是 Meta 排序，不是按讚排名；UI 不顯示假數字
- **App Review 時間不可控**：1–4 週；期間系統在 dev 模式可運作
- **爬蟲路線**：Meta ToS 禁止，台灣無美國判例保障；僅在 Apify 等付費服務上酌情使用

## 下一步（驗證通過後）

1. 部署 VPS（rsync → install.sh → cloudflared → Access）
2. 切 `mode=live` → 跑召回測試
3. 觀察兩週 → 調整關鍵字與排除詞 → 決定是否加 Apify／廠商做 FB
