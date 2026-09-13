"""周边 POI：美食 + 景点合并推荐"""
from typing import Any, Callable, Dict, Optional, Tuple

FOOD_SEARCH = {"keywords": "美食", "types": "050000", "radius": 2000}
SIGHT_SEARCH = {"keywords": "景点", "types": "110000", "radius": 3000}


def _parse_center(location: str) -> Dict[str, Any]:
    parts = location.split(",", 1)
    lng, lat = float(parts[0]), float(parts[1])
    return {
        "name": "当前位置",
        "location": location,
        "lnglat": [lng, lat],
    }


def merge_poi_maps(
    food_map: Optional[Dict[str, Any]],
    sight_map: Optional[Dict[str, Any]],
    location: str,
) -> Optional[Dict[str, Any]]:
    """合并美食与景点 POI 为单一 poi_map。"""
    food_pois = (food_map or {}).get("pois") or []
    sight_pois = (sight_map or {}).get("pois") or []
    if not food_pois and not sight_pois:
        return None

    center = (
        (food_map or {}).get("center")
        or (sight_map or {}).get("center")
        or _parse_center(location)
    )

    pois = []
    for p in food_pois[:6]:
        item = dict(p)
        item["category"] = "food"
        item["display_name"] = item.get("name", "")
        pois.append(item)
    for p in sight_pois[:6]:
        item = dict(p)
        item["category"] = "sight"
        item["display_name"] = item.get("name", "")
        pois.append(item)

    merged = {
        "type": "poi_map",
        "title": "周边美食与景点",
        "center": center,
        "pois": pois,
        "food_count": len(food_pois[:6]),
        "sight_count": len(sight_pois[:6]),
    }
    if (food_map or {}).get("offline") or (sight_map or {}).get("offline"):
        merged["offline"] = True
    return merged


def fetch_merged_nearby(
    location: str,
    call_mcp_tool: Callable[..., str],
    parse_poi_map_result: Callable[[str], Tuple[Optional[Dict], str]],
    get_cached_poi: Callable[[str, str], Optional[Dict]],
    cache_poi: Callable[[str, str, Dict], str],
    page_size: int = 6,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """并行逻辑上依次拉取美食/景点并合并。"""

    def fetch_category(params: Dict[str, Any], cache_key: str) -> Tuple[Optional[Dict], str]:
        args = {"location": location, "page_size": page_size, **params}
        raw = call_mcp_tool("amap_place_around", args)
        parsed, summary = parse_poi_map_result(raw)
        if parsed:
            cache_poi(location, cache_key, {"parsed": parsed, "summary": summary})
            return parsed, summary
        cached = get_cached_poi(location, cache_key)
        if cached and cached.get("parsed"):
            offline = dict(cached["parsed"])
            offline["offline"] = True
            return offline, f"{cached.get('summary', '')}\n（离线缓存数据）"
        return parsed, summary

    food_map, food_summary = fetch_category(FOOD_SEARCH, "美食")
    sight_map, sight_summary = fetch_category(SIGHT_SEARCH, "景点")
    merged = merge_poi_maps(food_map, sight_map, location)

    parts = []
    if food_summary:
        parts.append(f"【周边美食】\n{food_summary}")
    if sight_summary:
        parts.append(f"【周边景点】\n{sight_summary}")
    summary = "\n\n".join(parts) if parts else "未找到周边推荐"
    return merged, summary
