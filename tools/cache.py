"""MCP 工具结果 TTL 缓存"""
import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

DEFAULT_TTL = int(os.getenv("TOOL_CACHE_TTL", "300"))


class ToolResultCache:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL):
        self.ttl = ttl_seconds
        self._store: Dict[str, Dict[str, Any]] = {}

    def _key(self, tool_name: str, params: Dict[str, Any]) -> str:
        raw = json.dumps({"tool": tool_name, "params": params}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        key = self._key(tool_name, params)
        entry = self._store.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > self.ttl:
            del self._store[key]
            return None
        return entry["value"]

    def set(self, tool_name: str, params: Dict[str, Any], value: str) -> None:
        key = self._key(tool_name, params)
        self._store[key] = {"value": value, "ts": time.time()}

    def clear(self) -> None:
        self._store.clear()


_global_cache: Optional[ToolResultCache] = None


def get_tool_cache() -> ToolResultCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = ToolResultCache()
    return _global_cache
