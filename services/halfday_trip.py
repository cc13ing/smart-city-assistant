"""基于当前位置的半日游：选点 + 真实路网路线"""
import re
from typing import Any, Callable, Dict, List, Optional, Set

RouteFn = Callable[[str, str, str], Optional[Dict[str, Any]]]
PoiFn = Callable[[], Optional[Dict[str, Any]]]


def _norm_exclude(name: str) -> str:
    n = (name or "").strip()
    return re.sub(r"^第\d+站\s*", "", n)


def _parse_lnglat(loc: str) -> List[float]:
    lng, lat = loc.split(",")[:2]
    return [float(lng), float(lat)]

def _loc_str(poi: Dict[str, Any]) -> str:
    if poi.get("location"):
        return poi["location"]
    ll = poi.get("lnglat")
    if ll and len(ll) >= 2:
        return f"{ll[0]},{ll[1]}"
    return ""


def _is_excluded_poi(name: str, exclude_names: Set[str]) -> bool:
    if not exclude_names:
        return False
    n = (name or "").strip()
    if not n:
        return False
    for ex in exclude_names:
        if not ex:
            continue
        if ex == n or ex in n or n in ex:
            return True
    return False


def _pick_stops(
    pois: List[Dict[str, Any]],
    max_stops: int = 3,
    *,
    exclude_names: Optional[Set[str]] = None,
    skip_first: int = 0,
) -> List[Dict[str, Any]]:
    exclude_names = exclude_names or set()
    sorted_pois = sorted(pois, key=lambda p: int(p.get("distance") or 999999))
    pool: List[Dict[str, Any]] = []
    for poi in sorted_pois:
        name = (poi.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        if _is_excluded_poi(name, exclude_names):
            continue
        pool.append(poi)

    if skip_first > 0 and len(pool) > max_stops + skip_first:
        pool = pool[skip_first:]
    elif skip_first > 0 and len(pool) > max_stops:
        pool = pool[min(skip_first, len(pool) - max_stops) :]

    chosen: List[Dict[str, Any]] = []
    for poi in pool:
        name = (poi.get("name") or "").strip()
        if any(name in c.get("name", "") or c.get("name", "") in name for c in chosen):
            continue
        try:
            dist = int(poi.get("distance") or 0)
        except (TypeError, ValueError):
            dist = 0
        if dist < 400 and chosen:
            continue
        chosen.append(poi)
        if len(chosen) >= max_stops:
            break
    return chosen


def _merge_paths(segments: List[List[List[float]]]) -> List[List[float]]:
    merged: List[List[float]] = []
    for seg in segments:
        if not seg:
            continue
        if not merged:
            merged.extend(seg)
            continue
        start = seg[0]
        prev = merged[-1]
        if abs(prev[0] - start[0]) < 1e-6 and abs(prev[1] - start[1]) < 1e-6:
            merged.extend(seg[1:])
        else:
            merged.extend(seg)
    return merged


def _plan_segment(route_fn: RouteFn, origin: str, dest: str, mode: str) -> Optional[Dict[str, Any]]:
    seg = route_fn(origin, dest, mode)
    if seg and seg.get("path") and not seg.get("path_fallback"):
        return seg
    if mode != "walking":
        seg = route_fn(origin, dest, "walking")
        if seg and seg.get("path") and not seg.get("path_fallback"):
            return seg
    return seg


def build_halfday_trip_maps(
    origin_loc: str,
    origin_label: str,
    route_fn: RouteFn,
    poi_fn: PoiFn,
    mode: str = "driving",
    max_stops: int = 3,
    *,
    exclude_stop_names: Optional[List[str]] = None,
    skip_first: int = 0,
) -> Optional[Dict[str, Any]]:
    """返回 poi_map、route_map 及供 LLM 使用的上下文文本。"""
    if not origin_loc or "," not in origin_loc:
        return None

    poi_data = poi_fn()
    if not poi_data or not poi_data.get("pois"):
        return None

    exclude_set = {_norm_exclude(n) for n in (exclude_stop_names or []) if n}
    stops = _pick_stops(
        poi_data["pois"],
        max_stops=max_stops,
        exclude_names=exclude_set,
        skip_first=skip_first,
    )
    if not stops:
        return None

    try:
        origin_lnglat = _parse_lnglat(origin_loc)
    except (ValueError, TypeError):
        return None

    origin_name = origin_label or "当前位置"
    segments_meta: List[Dict[str, Any]] = []
    path_segments: List[List[List[float]]] = []
    total_distance = 0
    total_duration = 0

    chain = [{"name": origin_name, "location": origin_loc, "lnglat": origin_lnglat}] + [
        {
            "name": s.get("name", f"第{i + 1}站"),
            "location": _loc_str(s),
            "lnglat": s.get("lnglat") or _parse_lnglat(_loc_str(s)),
        }
        for i, s in enumerate(stops)
        if _loc_str(s)
    ]

    if len(chain) < 2:
        return None

    for i in range(len(chain) - 1):
        a, b = chain[i], chain[i + 1]
        seg = _plan_segment(route_fn, a["location"], b["location"], mode)
        if not seg or not seg.get("path"):
            continue
        path_segments.append(seg["path"])
        try:
            total_distance += int(seg.get("distance") or 0)
        except (TypeError, ValueError):
            pass
        try:
            total_duration += int(seg.get("duration") or 0)
        except (TypeError, ValueError):
            pass
        segments_meta.append(
            {
                "from": a["name"],
                "to": b["name"],
                "distance": seg.get("distance"),
                "duration_text": seg.get("duration_text", ""),
                "mode": seg.get("mode", mode),
            }
        )

    full_path = _merge_paths(path_segments)
    if len(full_path) < 3:
        return None

    last = chain[-1]
    stop_names = [s["name"] for s in chain[1:]]

    route_map: Dict[str, Any] = {
        "type": "route",
        "trip_type": "halfday",
        "mode": mode,
        "mode_label": {"driving": "驾车", "walking": "步行", "transit": "公交", "riding": "骑行"}.get(
            mode, "路线"
        ),
        "origin": {
            "name": origin_name,
            "location": origin_loc,
            "lnglat": origin_lnglat,
        },
        "destination": {
            "name": last["name"],
            "location": last["location"],
            "lnglat": last["lnglat"],
        },
        "stops": [
            {"order": idx + 1, "name": p["name"], "lnglat": p["lnglat"], "location": p["location"]}
            for idx, p in enumerate(chain[1:-1])
        ],
        "path": full_path,
        "path_fallback": False,
        "distance": total_distance,
        "duration_text": _format_duration(total_duration),
        "segments": segments_meta,
        "summary": f"半日游路线：{origin_name} → {' → '.join(stop_names)}",
    }
    from services.amap_uri import attach_navi_uri

    attach_navi_uri(route_map)

    poi_map: Dict[str, Any] = {
        "type": "poi_map",
        "title": "半日游途经点",
        "show_path": False,
        "center": {
            "name": origin_name,
            "location": origin_loc,
            "lnglat": origin_lnglat,
        },
        "pois": [
            {
                "name": f"第{idx + 1}站 {p['name']}",
                "display_name": p["name"],
                "address": stops[idx].get("address", ""),
                "type": stops[idx].get("type", "景点"),
                "location": p["location"],
                "lnglat": p["lnglat"],
                "distance": stops[idx].get("distance", ""),
                "poi_id": stops[idx].get("poi_id") or stops[idx].get("id", ""),
                "id": stops[idx].get("poi_id") or stops[idx].get("id", ""),
            }
            for idx, p in enumerate(chain[1:])
        ],
    }

    context_lines = [
        "【半日游结构化路线数据】",
        f"起点：{origin_name}（{origin_loc}）",
        f"途经：{' → '.join(stop_names)}",
        f"总距离约 {total_distance} 米，预计 {route_map['duration_text']}",
    ]
    for seg in segments_meta:
        context_lines.append(
            f"  · {seg['from']} → {seg['to']}（{seg.get('duration_text') or ''}）"
        )
    context_lines.append("请基于以上真实路线数据，输出详细半日游文字行程（含各站游览建议）。")

    return {
        "poi_map": poi_map,
        "route_map": route_map,
        "context_text": "\n".join(context_lines),
    }


def _format_duration(seconds: Any) -> str:
    try:
        sec = int(seconds)
    except (TypeError, ValueError):
        return str(seconds) if seconds else ""
    if sec < 60:
        return f"{sec}秒"
    mins = sec // 60
    if mins < 60:
        return f"{mins}分钟"
    h, m = divmod(mins, 60)
    return f"{h}小时{m}分钟" if m else f"{h}小时"
