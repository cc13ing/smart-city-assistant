"""高德 URI 导航链接构建"""
from typing import Any, Dict, Optional
from urllib.parse import quote

MODE_MAP = {
    "driving": "car",
    "car": "car",
    "walking": "walk",
    "walk": "walk",
    "transit": "bus",
    "bus": "bus",
    "riding": "ride",
    "ride": "ride",
}


def _point_segment(
    lnglat: Optional[list],
    location: str,
    name: str,
    fallback: str,
) -> Optional[str]:
    lng = lat = None
    if lnglat and len(lnglat) >= 2:
        lng, lat = lnglat[0], lnglat[1]
    elif location and "," in location:
        parts = location.split(",", 1)
        try:
            lng, lat = float(parts[0]), float(parts[1])
        except ValueError:
            return None
    if lng is None or lat is None:
        return None
    label = quote((name or fallback or "").strip() or fallback, safe="")
    return f"{lng},{lat},{label}"


def build_amap_navi_uri(
    origin: Dict[str, Any],
    destination: Dict[str, Any],
    mode: str = "driving",
) -> Optional[str]:
    """构建含起点/终点/出行方式的高德导航 URI。"""
    if not destination:
        return None
    to_seg = _point_segment(
        destination.get("lnglat"),
        destination.get("location", ""),
        destination.get("name", ""),
        "终点",
    )
    if not to_seg:
        return None
    m = MODE_MAP.get(mode, "car")
    parts = [
        f"to={to_seg}",
        f"mode={m}",
        "coordinate=gaode",
        "callnative=1",
        "src=AutoCityIntro",
    ]
    from_seg = _point_segment(
        origin.get("lnglat") if origin else None,
        (origin or {}).get("location", ""),
        (origin or {}).get("name", ""),
        "起点",
    )
    if from_seg:
        parts.insert(0, f"from={from_seg}")
    if m == "car":
        parts.append("policy=0")
    return f"https://uri.amap.com/navigation?{'&'.join(parts)}"


def attach_navi_uri(route_payload: Dict[str, Any]) -> Dict[str, Any]:
    if route_payload.get("type") == "route":
        uri = build_amap_navi_uri(
            route_payload.get("origin") or {},
            route_payload.get("destination") or {},
            route_payload.get("mode", "driving"),
        )
        if uri:
            route_payload["amap_navi_uri"] = uri
    return route_payload


def build_taxi_uri(lng: float, lat: float, name: str = "目的地") -> str:
    label = quote((name or "目的地").strip(), safe="")
    return f"https://uri.amap.com/taxi?dlat={lat}&dlon={lng}&dname={label}&dev=0&callnative=1"
