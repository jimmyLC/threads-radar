"""示範資料：python -m radar.demo　清除：python -m radar.demo --wipe

灌一批假的貼文（id 以 demo_ 開頭），讓你在拿到 Meta 權限之前先看 UI 長怎樣。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from . import db
from .config import load_keywords

# (小時前, 關鍵字們, 暱稱, 內文, 摘要, is_top, is_reply)
DATA = [
    (2, ["OpenAI", "AI"], "@demo_mira",
     "OpenAI 真的要開源了？官方預告會釋出一個 open-weight 模型，社群整個炸開。有人喊 Free tier 有救，有人在算自己顯卡跑不跑得動。",
     "OpenAI 預告釋出開源權重模型", 1, 0),
    (3, ["AI"], "@demo_river",
     "今天整個 feed 都是 AI Agent 框架比較文。我的結論：demo 都很神，上線都被 edge case 打死，fallback 沒寫的都出事了。",
     "Agent 框架 demo 與上線有落差", 0, 0),
    (4, ["LLM", "AI"], "@demo_sam",
     "Big tech 的 hiring freeze 現在都包裝成 'AI transformation'。same headcount, new buzzword.",
     "凍結職缺包裝成 AI 轉型", 0, 0),
    (5, ["ChatGPT", "AI"], "@demo_kai",
     "ChatGPT 的記憶功能開始主動引用上週的對話，有點毛但也有點方便。剛剛它直接說『你上次問過類似的問題』。",
     "ChatGPT 記憶功能變得更主動", 0, 0),
    (7, ["Claude", "Anthropic"], "@demo_iris",
     "Claude 寫長文還是最穩，尤其是維持格式的能力。其他家追得很快，但語感就是差一截，改稿時間明顯變長。",
     "Claude 長文穩定度仍領先", 1, 0),
    (8, ["DeepSeek"], "@demo_nico",
     "DeepSeek 新版數學題全對，價格又是別人的零頭。它們的商業邏輯我真的看不懂，但 API 用戶是真的爽到。",
     "DeepSeek 低價高效衝擊市場", 0, 0),
    (10, ["Gemini"], "@demo_lily",
     "Gemini 跟 Android 的整合越來越深，直接幫我摘要通知。大約七成準，錯的都是把促銷通知判成重要事項。",
     "Gemini 深度整合 Android", 0, 0),
    (12, ["LLM"], "@demo_hank",
     "LLM 靈異現象：同一個 prompt 早上跑正常、晚上跑就幻覺，temperature 明明是 0。有人遇過嗎？",
     "LLM 輸出不穩定的疑慮", 0, 1),
    (13, ["LLM"], "@demo_vic",
     "這是幻覺沒錯，我們查過是 logits processor 的 bug，升版本就好。", "回覆：幻覺源於版本 bug", 0, 0),
    (14, ["AI Agent"], "@demo_jo",
     "我們公司用 AI Agent 自動回客服信，三個月省下兩個人力，但壞掉的時候也很精彩，直接把折價碼送出去了。",
     "Agent 客服實測省兩個人力", 1, 0),
    (18, ["AGI", "OpenAI"], "@demo_ray",
     "Altman 又在講 AGI 時程。講了三年了，先把手上的產品穩定性做好再說好嗎。",
     "質疑 AGI 時程宣傳", 0, 1),
    (20, ["生成式AI"], "@demo_yu",
     "客戶已經分不出廣告素材是攝影棚拍的還是生成式AI做的，製片公司最近都在轉型做『指導AI』的業務。",
     "生成式AI 素材難辨真偽", 0, 0),
    (22, ["Anthropic"], "@demo_dan",
     "Anthropic 的 enterprise 定價公布，比我預期貴兩倍，但銷售說 uptime 有 99.9%。真的會有人為 uptime 買單嗎？會。我們就買了。",
     "Anthropic 企業方案偏貴但穩", 0, 0),
    (26, ["AI"], "@demo_pen",
     "AI 主播播晨間新聞一個月了，口誤率比真人低，但緊急事故的臨場反應還是零。", "AI 主播穩定但缺臨場反應", 0, 0),
    (30, ["ChatGPT", "AI Agent"], "@demo_wen",
     "用 ChatGPT 做 meeting notes 三個月的結論：逐字稿 95 分、待辦事項 60 分、保密條款要自己簽自己注意。",
     "ChatGPT 會議記錄實用心得", 0, 0),
    (34, ["Gemini", "AI"], "@demo_fan",
     "Gemini 的長文件功能拿來讀法規超好用，一百多頁的 PDF 秒出重點，法務同事已回不去了。", "Gemini 長文件整理好用", 1, 0),
    (40, ["人工智慧"], "@demo_twn",
     "政府說要投入人工智慧主權算力，口号很響，但電力問題先解決再談，不然都是畫大餅。", "主權算力需先解決電力", 0, 0),
    (46, ["DeepSeek", "LLM"], "@demo_chen",
     "把 DeepSeek 接進內部知識庫，中文召回比某家美系模型好，但英文技術文檔就明顯弱一截。混用才是正解。",
     "DeepSeek 中文召回表現佳", 0, 0),
    (52, ["Claude"], "@demo_ada",
     "Claude 的 Projects 功能根本是團隊知識庫的解答，新進同事不用再問我十次流程了。", "Claude Projects 利於知識傳承", 0, 0),
    (58, ["AI Agent"], "@demo_zoe",
     "Agent + 瀏覽器操作是今年的最大騙局還是最大商機？我各押一半，實測下單成功率六成，再看看。", "瀏覽器 Agent 成功率僅六成", 0, 0),
    (63, ["OpenAI"], "@demo_kyle",
     "OpenAI 的 DevDay 大招是 realtime API 降價，語音應用成本直接砍半，做客服機器人的要重新算帳了。", "Realtime API 降價利多語音應用", 1, 0),
    (70, ["ChatGPT"], "@demo_na",
     "學期末發現學生交的報告 ChatGPT 味越來越重，只好回頭考手寫。時代的眼淚。", "教界因 AI 回歸手寫考核", 0, 0),
    (72, ["生成式AI", "人工智慧"], "@demo_kk",
     "生成式AI 做的中配（中文配音）已經到商用水準，動畫公司開始裁配音組，這波真的是結構性失業。", "AI 配音衝擊配音產業", 0, 0),
    (73, ["大型語言模型"], "@demo_prof",
     "審到一篇論文把大型語言模型叫做 LLMs model，學術寫作的崩壞始於引用不足，終於術語亂用。", "論文術語亂用的抱怨", 0, 1),
    (75, ["AI"], "@demo_hw",
     "NVIDIA 財報會議九成都是在講 AI 資本支出，跟黃仁勳的皮衣一樣穩。資料中心營收又超預期。", "AI 資本支出推升 NVIDIA 營收", 0, 0),
    (95, ["OpenAI", "Gemini"], "@demo_vs",
     "同樣一份系統設計題丟給 OpenAI 和 Gemini：OpenAI 給的架構保守但穩，Gemini 給了三個方案還附風險表。我比較意外的是 token 用量差四倍。", "兩家模型解題風格比較", 1, 0),
]


def seed() -> None:
    db.init()
    now = datetime.now(timezone.utc)
    with db.connect() as c:
        if c.execute("SELECT COUNT(*) AS n FROM posts WHERE id LIKE 'demo%'").fetchone()["n"]:
            print("示範資料已存在，先執行 --wipe 再重新灌。")
            return
        terms = {k["term"]: k["id"] for k in c.execute("SELECT id, term FROM keywords")}
        n_posts = 0
        n_mentions = 0
        for i, (hours_ago, kws, author, text, summary, is_top, is_reply) in enumerate(DATA, 1):
            pid = f"demo_{i:04d}"
            posted = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "INSERT OR IGNORE INTO posts(id, author, text, permalink, posted_at, is_reply, topic_tag, summary, first_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (pid, author, text, f"https://www.threads.net/@demo/post/{pid}", posted, is_reply, None, summary, db.utcnow_str()),
            )
            n_posts += c.execute("SELECT changes()").fetchone()[0]
            for term in kws:
                kid = terms.get(term)
                if kid is None:
                    continue
                c.execute(
                    "INSERT OR IGNORE INTO mentions(post_id, keyword_id, is_top, window_hours, seen_at) VALUES(?,?,?,?,?)",
                    (pid, kid, is_top, 24, db.utcnow_str()),
                )
                n_mentions += 1
        db.set_setting(c, "demo", "1")
    print(f"✅ 已灌入示範資料：{n_posts} 則貼文、{n_mentions} 筆提及。開啟網頁即可瀏覽。")


def wipe() -> None:
    db.init()
    with db.connect() as c:
        c.execute("DELETE FROM posts WHERE id LIKE 'demo%'")
        db.set_setting(c, "demo", "0")
    print("✅ 示範資料已清除。")


def seed_keyword(term: str, kid: int) -> int:
    """示範模式下新增關鍵字時，灌 2 則該關鍵字的假貼文（讓即時搜尋的體驗完整）。"""
    now = datetime.now(timezone.utc)
    templates = [
        (1, 1, f"最近整個時間線都在聊 {term}，連我阿嬤都問我這是什麼。認真說：熱度是真的，深度討論要去留言區挖。",
         f"{term} 成為熱門話題"),
        (5, 0, f"試用一輪 {term} 相關的新工具，結論是前期興奮、後期回歸平凡，實際導入流程才是真正的門檻。",
         f"{term} 工具實測心得"),
    ]
    made = 0
    stamp = int(now.timestamp())
    with db.connect() as c:
        for j, (hours_ago, is_top, text, summary) in enumerate(templates):
            pid = f"demo_kw_{kid}_{stamp}_{j}"
            posted = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "INSERT OR IGNORE INTO posts(id, author, text, permalink, posted_at, is_reply, topic_tag, summary, first_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (pid, "@demo_watcher", text, f"https://www.threads.net/@demo/post/{pid}", posted, 0, None, summary, db.utcnow_str()),
            )
            c.execute(
                "INSERT OR IGNORE INTO mentions(post_id, keyword_id, is_top, window_hours, seen_at) VALUES(?,?,?,?,?)",
                (pid, kid, is_top, 24, db.utcnow_str()),
            )
            made += 1
    print(f"[demo] 為新關鍵字「{term}」灌入 {made} 則示範貼文", flush=True)
    return made


def main() -> int:
    if "--wipe" in sys.argv:
        wipe()
    else:
        seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
