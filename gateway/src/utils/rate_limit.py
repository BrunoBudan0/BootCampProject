import threading
import time
from collections import deque


class RateLimiter:
    # janela deslizante em memória: vale por processo, o que basta para o protótipo
    def __init__(self) -> None:
        self._hits: dict[tuple, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: tuple, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


limiter = RateLimiter()
