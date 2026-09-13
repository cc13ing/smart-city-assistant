"""地点关键字解析（高德 POI 搜索）"""
import os
import re
from typing import Any, Dict, Optional

import requests

from services.route_destination import (
    _city_for_destination,
    geocode_search_keywords,
    should_bias_geocode_to_near,
    _normalize_poi_name,
)

AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")


def _is_coordinate(text: str) -> bool:
    return bool(re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*$", text.strip()))


def _parse_lnglat(loc: str):
    lng, lat = loc.split(",", 1)[:2]
    return float(lng), float(lat)


def _haversine_meters(a, b) -> float:
    from math import asin, cos, radians, sin, sqrt

    lng1, lat1 = a
    lng2, lat2 = b
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    x = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(x))


def _pick_nearest_poi(pois, near: str):
    if not near or not _is_coordinate(near) or len(pois) <= 1:
        return pois[0]
    try:
        origin = _parse_lnglat(near)

        def dist(p):
            loc = p.get("location", "")
            if not loc or "," not in loc:
                return float("inf")
            return _haversine_meters(origin, _parse_lnglat(loc))

        return min(pois, key=dist)
    except (ValueError, TypeError):
        return pois[0]


def resolve_place(keywords: str, city: str = "", near: str = "") -> Dict[str, Any]:
    """将地名或地址解析为结构化 POI，含 lnglat。"""
    raw_kw = _normalize_poi_name((keywords or "").strip())
    if not raw_kw:
        return {"error": "请输入目的地"}

    kw = geocode_search_keywords(raw_kw) or raw_kw
    city = _city_for_destination(raw_kw, city)
    if not should_bias_geocode_to_near(raw_kw):
        near = ""

    if _is_coordinate(kw):
        parts = kw.split(",", 1)
        lng, lat = float(parts[0]), float(parts[1])
        return {
            "name": "目的地",
            "location": kw,
            "lnglat": [lng, lat],
            "address": "",
            "city": city or "",
        }

    if not AMAP_API_KEY:
        return {"error": "未配置高德地图 API 密钥"}

    params = {
        "key": AMAP_API_KEY,
        "keywords": kw,
        "page_size": 10 if near else 1,
        "output": "JSON",
    }
    if city:
        params["city"] = city
        params["citylimit"] = "true"

    try:
        resp = requests.get(
            "https://restapi.amap.com/v5/place/text",
            params=params,
            timeout=10,
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("pois"):
            return {"error": f"未找到「{kw}」，请换个名称试试"}
        poi = _pick_nearest_poi(data["pois"], near)
        location = poi.get("location", "")
        if not location or "," not in location:
            return {"error": f"未获取到「{kw}」的坐标"}
        lng, lat = location.split(",", 1)
        return {
            "name": poi.get("name", kw),
            "location": location,
            "lnglat": [float(lng), float(lat)],
            "address": poi.get("address", ""),
            "city": city or poi.get("cityname", ""),
        }
    except Exception as e:
        return {"error": f"解析地点时出错：{e}"}
