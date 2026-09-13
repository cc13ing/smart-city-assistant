"""实时伴游：下一站建议 + 全程 geofence 跟踪。

行程数据来自 /api/trips（半日游多由 local_scout 预取 + 会话保存），
与 active_agent 解耦；伴游只依赖 trip.stops 坐标，不重复调用子 Agent。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_GEOFENCE_METERS = 120


def _parse_lnglat(location: str) -> Optional[Tuple[float, float]]:
    if not location or "," not in location:
        return None
    try:
        lng, lat = location.split(",", 1)[:2]
        return float(lng.strip()), float(lat.strip())
    except ValueError:
        return None


def haversine_meters(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lng1, lat1 = a
    lng2, lat2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def stop_lnglat(stop: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    ll = stop.get("lnglat")
    if isinstance(ll, (list, tuple)) and len(ll) >= 2:
        return float(ll[0]), float(ll[1])
    loc = stop.get("location") or ""
    return _parse_lnglat(loc)


def suggest_next_stop(
    pois: List[Dict[str, Any]],
    hour: Optional[int] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """根据时段与画像权重推荐下一站。"""
    hour = hour if hour is not None else datetime.now().hour
    if not pois:
        return {"suggestion": "暂无周边 POI，请开启定位或换个区域试试。", "poi": None}

    if profile:
        from services.feedback import apply_weights_to_pois

        pois = apply_weights_to_pois(pois, profile)

    if hour < 11:
        period, hint = "morning", "上午适合游览景点"
    elif hour < 14:
        period, hint = "noon", "午餐时间，推荐附近餐饮"
        food = [p for p in pois if "餐" in p.get("type", "") or "美食" in p.get("name", "")]
        if food:
            poi = food[0]
            return _pack(poi, period, hint, "建议午餐去这里")
    elif hour < 18:
        period, hint = "afternoon", "下午可以继续逛景点"
    else:
        period, hint = "evening", "晚上可品尝本地美食"
        food = [p for p in pois if "餐" in p.get("type", "") or "美食" in p.get("name", "")]
        if food:
            poi = food[0]
            return _pack(poi, period, hint, "晚餐推荐")

    poi = pois[0]
    return _pack(poi, period, hint, "下一站建议")


def _pack(poi: Dict[str, Any], period: str, hint: str, prefix: str) -> Dict[str, Any]:
    name = poi.get("name", "未知地点")
    return {
        "suggestion": f"{prefix}：{name}。{hint}。",
        "period": period,
        "poi": poi,
        "arrival_hint": f"到达 {name} 后可拍照打卡或查看详情",
        "queue_hint": "高峰时段可能排队，建议错峰",
        "closure_hint": "闭馆时间以现场公告为准，出发前请确认",
    }


def track_companion(
    location: str,
    trip: Optional[Dict[str, Any]] = None,
    *,
    geofence_meters: float = DEFAULT_GEOFENCE_METERS,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    全程伴游：检测是否到达当前站点、推进进度、返回下一站与距离。
    """
    pos = _parse_lnglat(location)
    if not pos:
        return {"ok": False, "message": "无效坐标，请重新定位", "mode": "idle"}

    if not trip or not (trip.get("stops") or []):
        return {
            "ok": True,
            "mode": "explore",
            "message": "未选择行程，可创建或收藏行程后开启全程伴游",
            "location": location,
            "progress": None,
        }

    stops: List[Dict[str, Any]] = list(trip.get("stops") or [])
    active_idx = int(trip.get("active_stop_index") or 0)
    active_idx = max(0, min(active_idx, len(stops) - 1))

    distances = []
    for i, stop in enumerate(stops):
        sll = stop_lnglat(stop)
        d = haversine_meters(pos, sll) if sll else None
        distances.append({"index": i, "name": stop.get("name"), "distance_m": round(d) if d is not None else None})

    current = stops[active_idx]
    cur_ll = stop_lnglat(current)
    dist_to_current = haversine_meters(pos, cur_ll) if cur_ll else None

    arrived = dist_to_current is not None and dist_to_current <= geofence_meters
    event = None
    if arrived and not current.get("visited"):
        event = {
            "type": "arrived",
            "stop_index": active_idx,
            "stop_name": current.get("name"),
            "message": f"您已到达「{current.get('name')}」，可以开始游览",
        }
        current["visited"] = True
        if active_idx < len(stops) - 1:
            active_idx += 1

    next_stop = stops[active_idx] if active_idx < len(stops) else None
    next_ll = stop_lnglat(next_stop) if next_stop else None
    dist_next = haversine_meters(pos, next_ll) if next_ll and next_stop else None

    completed = sum(1 for s in stops if s.get("visited"))
    progress = {
        "completed": completed,
        "total": len(stops),
        "active_index": active_idx,
        "percent": round(100 * completed / len(stops)) if stops else 0,
    }

    message_parts = []
    if event:
        message_parts.append(event["message"])
    if next_stop and not (event and active_idx >= len(stops) - 1 and current.get("visited")):
        dn = f"{int(dist_next)}米" if dist_next is not None else "—"
        message_parts.append(f"下一站：{next_stop.get('name')}（约 {dn}）")
    elif completed >= len(stops):
        message_parts.append("恭喜，您已完成本行程全部站点！")

    from services.poi_guide import guide_snippet_for_llm

    culture = guide_snippet_for_llm(next_stop.get("name", "")) if next_stop else ""

    return {
        "ok": True,
        "mode": "trip",
        "trip_id": trip.get("trip_id"),
        "event": event,
        "arrived": arrived,
        "distance_to_next_m": round(dist_next) if dist_next is not None else None,
        "next_stop": next_stop,
        "progress": progress,
        "distances": distances,
        "active_stop_index": active_idx,
        "stops": stops,
        "message": " ".join(message_parts) or "继续向下一站前进吧",
        "culture_hint": culture,
        "status": "completed" if completed >= len(stops) else "in_progress",
    }
