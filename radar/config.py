"""設定載入：.env、keywords.yaml、exclusions.yaml"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def db_path() -> Path:
    return Path(os.getenv("RADAR_DB", str(BASE_DIR / "data" / "radar.db")))


def config_dir() -> Path:
    return Path(os.getenv("RADAR_CONFIG_DIR", str(BASE_DIR / "config")))


def _load_list(filename: str, key: str) -> list[str]:
    path = config_dir() / filename
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(x).strip() for x in (data.get(key) or []) if str(x).strip()]


def load_keywords() -> list[str]:
    return _load_list("keywords.yaml", "keywords")


def load_exclusions() -> list[str]:
    return _load_list("exclusions.yaml", "exclusions")


# Threads Graph API
GRAPH_BASE = os.getenv("THREADS_GRAPH_BASE", "https://graph.threads.com").rstrip("/")
GRAPH_VERSION = os.getenv("THREADS_GRAPH_VERSION", "v1.0")
APP_ID = os.getenv("THREADS_APP_ID", "")
APP_SECRET = os.getenv("THREADS_APP_SECRET", "")
REDIRECT_URI = os.getenv("THREADS_REDIRECT_URI", "http://localhost:8899/callback")

# LLM（OpenAI 相容）
LLM_API_BASE = os.getenv("LLM_API_BASE", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

# 其他
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "8"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "365"))
