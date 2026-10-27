"""
ratelimit.py  —  limits how often one visitor can call an endpoint.

Why: (1) every chat question costs us a call to the language model, so one
person must not be able to run up the bill; (2) it slows down anyone who tries
to guess access codes.  It keeps a short list of recent request times per
visitor address and refuses once the list is too long.
"""

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._calls = defaultdict(list)
        self._since_cleanup = 0

    def allow(self, key: str, now: float = None) -> bool:
        now = time.time() if now is None else now
        recent = [t for t in self._calls[key] if now - t < self.window]
        if len(recent) >= self.limit:
            self._calls[key] = recent
            return False
        recent.append(now)
        self._calls[key] = recent
        self._since_cleanup += 1
        if self._since_cleanup >= 500:          # forget visitors we have not seen for a while
            self._cleanup(now)
        return True

    def _cleanup(self, now: float):
        for key in [k for k, v in self._calls.items() if not v or now - v[-1] >= self.window]:
            del self._calls[key]
        self._since_cleanup = 0
