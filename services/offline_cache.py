"""离线/弱网：POI 与路线本地缓存"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_DIR = Path(os.getenv("OFFLINE_CACHE_DIR", "data/cache"))
DEFAULT_TTL = int(os.getenv("OFFLINE_CACHE_TTL", "86400"))


def _cache_path(category: str, key: str) -> Path:
    return CACHE_DIR / category / f"{key}.json"


def _make_key(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def save_cache(category: str, key_parts: tuple, data: Any, ttl: int = DEFAULT_TTL) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cat_dir = CACHE_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    key = _make_key(*key_parts)
    path = _cache_path(category, key)
    payload = {"saved_at": time.time(), "ttl": ttl, "data": data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return key


def load_cache(category: str, key_parts: tuple) -> Optional[Any]:
    key = _make_key(*key_parts)
    path = _cache_path(category, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - payload.get("saved_at", 0) > payload.get("ttl", DEFAULT_TTL):
            path.unlink(missing_ok=True)
            return None
        return payload.get("data")
    except (json.JSONDecodeError, OSError):
        return None


def cache_poi(location: str, keywords: str, data: Dict[str, Any]) -> str:
    return save_cache("poi", (location, keywords), data)


def get_cached_poi(location: str, keywords: str) -> Optional[Dict[str, Any]]:
    return load_cache("poi", (location, keywords))


def cache_route(origin: str, destination: str, mode: str, data: Dict[str, Any]) -> str:
    return save_cache("route", (origin, destination, mode), data)


def get_cached_route(origin: str, destination: str, mode: str) -> Optional[Dict[str, Any]]:
    return load_cache("route", (origin, destination, mode))


def cache_poi_detail(keywords: str, city: str, data: Dict[str, Any]) -> str:
    return save_cache("poi_detail", (keywords, city), data, ttl=int(os.getenv("OFFLINE_CACHE_TTL", "86400")))


def get_cached_poi_detail(keywords: str, city: str = "") -> Optional[Dict[str, Any]]:
    return load_cache("poi_detail", (keywords, city))
