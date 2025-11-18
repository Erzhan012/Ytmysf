import html

def sanitize_title(title: str) -> str:
    """
    Убираем слово YouTube (если есть) и экранируем для HTML.
    """
    if not title:
        return ""
    cleaned = title.replace("YouTube", "").strip()
    return html.escape(cleaned)

def format_duration(seconds) -> str:
    """
    Форматирует длительность в секунды в строку M:SS или H:MM:SS
    """
    if seconds is None:
        return ""
    try:
        s = int(seconds)
    except Exception:
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"
