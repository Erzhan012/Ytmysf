import os
import tempfile
from typing import List, Dict, Any, Optional
from yt_dlp import YoutubeDL

def _make_ydl_opts_for_search():
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": True,  # быстрее — не заходить глубоко
        "restrictfilenames": True,
    }

def _make_ydl_opts_for_info():
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

def _make_ydl_opts_for_download(out_dir: str):
    return {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
        ],
    }

def _normalize_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализуем разные структуры entry в единый словарь"""
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or raw.get("name"),
        "webpage_url": raw.get("webpage_url") or raw.get("url") or raw.get("original_url"),
        "duration": raw.get("duration"),
        "uploader": raw.get("uploader") or raw.get("uploader_id") or raw.get("channel"),
        "source": raw.get("extractor") or raw.get("extractor_key"),
        "_raw": raw,
    }

def search_combined(query: str, sources: List[str], max_results_total: int = 50) -> List[Dict[str, Any]]:
    """
    Выполняет комбинированный поиск по префиксам sources.
    Возвращает список нормализованных entries (id, title, webpage_url, duration, uploader, source).
    Работает синхронно — вызывайте в run_in_executor.
    """
    results: Dict[str, Dict[str, Any]] = {}
    per_source = max(5, int(max_results_total / max(1, len(sources))) + 2)
    ydl_opts = _make_ydl_opts_for_search()
    with YoutubeDL(ydl_opts) as ydl:
        for prefix in sources:
            query_string = f"{prefix}{per_source}:{query}"
            try:
                info = ydl.extract_info(query_string, download=False)
            except Exception:
                continue
            if not info:
                continue
            entries = info.get("entries") or []
            for e in entries:
                if not e:
                    continue
                key = e.get("id") or e.get("webpage_url") or e.get("title")
                if not key:
                    continue
                if key in results:
                    continue
                normalized = _normalize_entry(e)
                results[key] = normalized
            if len(results) >= max_results_total:
                break
    return list(results.values())[:max_results_total]

def fetch_info(url_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Извлекает подробную информацию для конкретного URL или id (не скачивая).
    Возвращает нормализованный entry или None.
    Работает синхронно — вызывать через run_in_executor.
    """
    ydl_opts = _make_ydl_opts_for_info()
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url_or_id, download=False)
        except Exception:
            return None
        if not info:
            return None
        # Если playlist — берём первый элемент (если есть)
        if info.get("entries"):
            first = info["entries"][0] if info["entries"] else None
            if first:
                return _normalize_entry(first)
        return _normalize_entry(info)

def download_to_mp3(url: str, out_dir: Optional[str] = None) -> Optional[str]:
    """
    Скачивает единичный трек по url (или id), конвертирует в mp3 и возвращает путь к mp3-файлу.
    Работает синхронно — вызывать в run_in_executor.
    """
    if out_dir is None:
        out_dir = tempfile.mkdtemp()
    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    ydl_opts = _make_ydl_opts_for_download(out_dir)
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None
            track_id = info.get("id")
            if track_id:
                expected = os.path.join(out_dir, f"{track_id}.mp3")
                if os.path.exists(expected):
                    return expected
            # fallback: найдём любой mp3 в директории
            for fname in os.listdir(out_dir):
                if fname.lower().endswith(".mp3"):
                    return os.path.join(out_dir, fname)
            return None
    except Exception:
        return None
