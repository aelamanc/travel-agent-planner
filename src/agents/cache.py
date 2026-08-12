"""TTL cache for MCP tool calls, keyed on (server, tool, normalized args) and
shared across a whole eval run — constructed once, threaded into every
domain agent, never reset between scenarios.

Only the orchestrated strategy uses this; the four control strategies call
BaseTool.run() directly with no caching layer at all. In mock mode, tool
calls are near-instant in-process dict lookups, so a hit here saves
negligible wall time regardless — cache_hit_rate should be read as a
property of the orchestrated run's own repeated-argument pattern, not as an
efficiency advantage over the controls (see ARCHITECTURE.md).
"""

import json
import time


class TTLCache:
    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple, tuple[dict, float]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(server: str, tool: str, args: dict) -> tuple:
        return (server, tool, json.dumps(args, sort_keys=True, default=str))

    def get(self, server: str, tool: str, args: dict) -> dict | None:
        key = self._key(server, tool, args)
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, server: str, tool: str, args: dict, value: dict) -> None:
        key = self._key(server, tool, args)
        self._store[key] = (value, time.monotonic() + self.ttl_seconds)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
