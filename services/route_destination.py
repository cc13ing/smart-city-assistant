"""路线终点消歧：优先使用行程/会话/画像中的本地 POI 坐标。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _normalize_poi_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"^第\d+站\s*", "", name)
    return name


_POI_NAME_PREFIX_OK = ("西安", "陕西", "中国", "小", "大", "新", "旧", "南", "北", "东", "西", "第")


def _substring_match_ok(query: str, candidate: str) -> bool:
    """允许「大雁塔」↔「大雁塔假日酒店」「西安钟楼」，拒绝「钟楼」↔「醒钟楼」。"""
    if query == candidate:
        return True
    if query not in candidate and candidate not in query:
        return False
    longer, shorter = (candidate, query) if len(candidate) >= len(query) else (query, candidate)
    if shorter not in longer:
        return False
    if longer == shorter:
        return True
    if longer.startswith(shorter) and len(shorter) >= 2:
        rest = longer[len(shorter) :]
        if not rest:
            return True
        if any(rest.startswith(p) for p in _POI_NAME_PREFIX_OK):
            return True
        if rest[0] in "酒店客栈门店楼苑园寺塔中心广场":
            return True
        return False
    if longer.endswith(shorter):
        prefix = longer[: len(longer) - len(shorter)]
        return any(prefix.startswith(p) for p in _POI_NAME_PREFIX_OK)
    return False


def names_match(query: str, candidate: str) -> bool:
    q = _normalize_poi_name(query)
    c = _normalize_poi_name(candidate)
    if not q or not c:
        return False
    if q == c:
        return True
    return _substring_match_ok(q, c) or _substring_match_ok(c, q)


def poi_location(poi: Dict[str, Any]) -> str:
    loc = (poi.get("location") or "").strip()
    if loc and "," in loc:
        return loc
    lnglat = poi.get("lnglat")
    if isinstance(lnglat, (list, tuple)) and len(lnglat) >= 2:
        return f"{lnglat[0]},{lnglat[1]}"
    return ""


def _scan_poi_candidates(dest_name: str, pois: List[Dict[str, Any]], source: str) -> Optional[Dict[str, str]]:
    for poi in pois or []:
        name = poi.get("name") or ""
        display = poi.get("display_name") or ""
        if not (names_match(dest_name, name) or (display and names_match(dest_name, display))):
            continue
        loc = poi_location(poi)
        if loc:
            label = display or _normalize_poi_name(name) or name
            return {"destination": loc, "name": label, "source": source}
    return None


def _scan_stops(dest_name: str, stops: List[Dict[str, Any]], source: str) -> Optional[Dict[str, str]]:
    return _scan_poi_candidates(dest_name, stops, source)


def find_destination_in_message(dest_name: str, msg: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if msg.get("role") != "assistant":
        return None
    trip = msg.get("trip_plan") or {}
    hit = _scan_stops(dest_name, trip.get("stops") or [], "trip_plan")
    if hit:
        return hit
    rm = msg.get("route_map") or {}
    dest = rm.get("destination") or {}
    if names_match(dest_name, dest.get("name", "")):
        loc = poi_location(dest)
        if loc:
            return {"destination": loc, "name": dest.get("name", ""), "source": "route_map_dest"}
    hit = _scan_stops(dest_name, rm.get("stops") or [], "route_map_stops")
    if hit:
        return hit
    pois = (msg.get("poi_map") or {}).get("pois") or []
    return _scan_poi_candidates(dest_name, pois, "poi_map")


def find_destination_in_history(dest_name: str, history: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    for msg in reversed(history or []):
        hit = find_destination_in_message(dest_name, msg)
        if hit:
            return hit
    return None


def find_destination_in_profile(dest_name: str, profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not profile:
        return None
    for poi in profile.get("recent_pois") or []:
        name = poi.get("name") or ""
        if not names_match(dest_name, name):
            continue
        loc = (poi.get("location") or "").strip()
        if loc:
            return {"destination": loc, "name": name, "source": "profile"}
    return None


def find_destination_in_state(
    dest_name: str,
    *,
    trip_plan: Optional[Dict[str, Any]] = None,
    route_map: Optional[Dict[str, Any]] = None,
    poi_map: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    fake_msgs = []
    if trip_plan:
        fake_msgs.append({"role": "assistant", "trip_plan": trip_plan})
    if route_map:
        fake_msgs.append({"role": "assistant", "route_map": route_map})
    if poi_map:
        fake_msgs.append({"role": "assistant", "poi_map": poi_map})
    return find_destination_in_history(dest_name, fake_msgs)


_XIAN_LANDMARK_HINTS = (
    "大雁塔",
    "钟楼",
    "鼓楼",
    "兵马俑",
    "大唐不夜城",
    "回民街",
    "城墙",
    "陕西历史博物馆",
    "华清池",
)

# 短地名在全国易重名，搜索时用更完整关键字 + 固定城市（仅精确地名命中）
_LANDMARK_GEOCODE_KEYWORDS: Dict[str, str] = {
    "钟楼": "西安钟楼",
    "鼓楼": "西安鼓楼",
    "城墙": "西安城墙",
    "回民街": "西安回民街",
}

# 杨陵/西农等本地地标：不得因含「钟楼」等子串被升格为西安知名景点
_LOCAL_LANDMARK_EXACT = frozenset(
    {
        "醒钟楼",
    }
)

# 仅精确匹配才视为西安地标（禁止「钟楼」in「醒钟楼」）
_XIAN_LANDMARK_EXACT = frozenset(_LANDMARK_GEOCODE_KEYWORDS.keys()) | frozenset(
    k for k in _XIAN_LANDMARK_HINTS if k not in _LANDMARK_GEOCODE_KEYWORDS
)


def is_local_landmark(name: str) -> bool:
    d = _normalize_poi_name(name)
    return bool(d) and d in _LOCAL_LANDMARK_EXACT


def is_xian_landmark_keyword(name: str) -> bool:
    d = _normalize_poi_name(name)
    if not d or is_local_landmark(d):
        return False
    if d in _XIAN_LANDMARK_EXACT:
        return True
    # 长地标允许带后缀：大雁塔假日酒店
    for hint in _XIAN_LANDMARK_HINTS:
        if len(hint) >= 4 and d != hint and d.startswith(hint):
            return True
    return False


def geocode_search_keywords(name: str) -> str:
    """供 POI 搜索 / 导航弹窗使用的消歧关键字。"""
    d = _normalize_poi_name(name)
    if not d:
        return ""
    if is_local_landmark(d):
        return d
    if d in _LANDMARK_GEOCODE_KEYWORDS:
        return _LANDMARK_GEOCODE_KEYWORDS[d]
    return d


def _city_for_destination(dest_name: str, default_city: str) -> str:
    """西安知名地标用西安 adcode 解析，避免在咸阳 GPS 下误匹配到机场/公交站。"""
    d = (dest_name or "").strip()
    if not d:
        return default_city
    if is_xian_landmark_keyword(d):
        return "西安"
    return default_city


def should_bias_geocode_to_near(name: str) -> bool:
    """西安知名地标全国搜索；本地地标（醒钟楼）或普通 POI 可优先距 GPS 最近。"""
    if is_local_landmark(name):
        return True
    return not is_xian_landmark_keyword(name)


def _history_hit_trusted(dest_name: str, hit: Dict[str, str]) -> bool:
    """会话/画像里缓存的同名 POI 是否可信。"""
    label = _normalize_poi_name(hit.get("name") or "")
    if is_local_landmark(dest_name) and is_xian_landmark_keyword(label):
        return False
    if dest_name == "钟楼" and "醒" in label:
        return False
    if is_xian_landmark_keyword(dest_name) and label and not _substring_match_ok(dest_name, label):
        if not is_xian_landmark_keyword(label):
            return False
    return True


def resolve_route_planning_args(
    dest_name: str,
    *,
    origin: str,
    mode: str = "driving",
    city: str = "",
    session_history: Optional[List[Dict[str, Any]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    trip_plan: Optional[Dict[str, Any]] = None,
    route_map: Optional[Dict[str, Any]] = None,
    poi_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构造 amap_route_planning 参数。
    若会话/画像/当前状态中有同名 POI 坐标，优先用坐标，避免全国重名误匹配。
    """
    search_name = geocode_search_keywords(dest_name) or dest_name
    args: Dict[str, Any] = {"origin": origin, "destination": search_name, "mode": mode}
    resolved_city = _city_for_destination(dest_name, city)
    if resolved_city:
        args["city"] = resolved_city

    hit = (
        find_destination_in_state(dest_name, trip_plan=trip_plan, route_map=route_map, poi_map=poi_map)
        or find_destination_in_history(dest_name, session_history or [])
        or find_destination_in_profile(dest_name, profile)
    )
    if hit and _history_hit_trusted(dest_name, hit):
        args["destination"] = hit["destination"]
        args["_resolved_name"] = hit["name"]
        args["_resolved_source"] = hit["source"]
    return args
