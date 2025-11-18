import os

from dotenv import load_dotenv

# Загружаем .env если он есть (локально)
load_dotenv()

def _parse_list_env(var: str, default):
    raw = os.getenv(var)
    if raw:
        # split by comma and strip
        return [s.strip() for s in raw.split(",") if s.strip()]
    return default

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else 0

# Поисковые префиксы yt-dlp (можно переопределить через SEARCH_SOURCES в .env, разделённые запятой)
SEARCH_SOURCES = _parse_list_env("SEARCH_SOURCES", [
    "ytsearch",
    "ytmusicsearch",
    "scsearch",
    "spsearch",
    "bandcampsearch",
    "deezersearch",
])

MAX_RESULTS_TOTAL = int(os.getenv("MAX_RESULTS_TOTAL", "30"))
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "10"))
SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", "3600"))
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/telegram_music_bot")
