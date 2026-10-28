"""LLM 一行摘要（OpenAI 相容 chat completions API）"""
from __future__ import annotations

import json
import re

import httpx

from .config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

BATCH = 20
SYSTEM = (
    "你是繁體中文編輯，替社群貼文撰寫一行摘要。"
    "規則：1) 不超過 30 個字 2) 只陳述貼文的主張，不評論真偽、不加自己的意見 "
    "3) 專有名詞與英文保留原文 4) 輸出只能是 JSON，不要有其他文字。"
)


def _extract_json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.MULTILINE)
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"回應中找不到 JSON：{s[:120]}")
    return json.loads(s[start : end + 1])


def summarize(posts: list[dict]) -> dict[str, str]:
    """輸入 [{"id","text"}]，回傳 {id: 摘要}。未設定 LLM 時回空字典。"""
    if not posts:
        return {}
    if not (LLM_API_KEY and LLM_API_BASE and LLM_MODEL):
        print("[summary] 未設定 LLM_API_BASE/KEY/MODEL，跳過摘要", flush=True)
        return {}

    out: dict[str, str] = {}
    for i in range(0, len(posts), BATCH):
        chunk = posts[i : i + BATCH]
        lines = "\n".join(f'{p["id"]}: {p["text"][:500]}' for p in chunk)
        payload = {
            "model": LLM_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"貼文清單（格式為 id: 內文）：\n\n{lines}\n\n"
                    '輸出 JSON 物件，key 是貼文 id，value 是該貼文的一行中文摘要。',
                },
            ],
        }
        resp = httpx.post(
            f"{LLM_API_BASE}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)
        for p in chunk:
            s = data.get(p["id"])
            if isinstance(s, str) and s.strip():
                out[p["id"]] = s.strip()[:60]
    return out
