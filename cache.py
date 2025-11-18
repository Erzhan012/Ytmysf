import time
from typing import Any, Dict, Optional

class TTLCache:
    """
    Простая реализация TTL-кэша в памяти.
    key -> (timestamp, value)
    """
    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._data: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._data.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self._ttl:
            # удаляем просроченную запись
            try:
                del self._data[key]
            except KeyError:
                pass
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.time(), value)

    def delete(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
