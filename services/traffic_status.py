"""高德实时路况查询（含未覆盖区域的降级方案）"""
from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional, Tuple

import requests

AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")

# 高德交通态势 REST API 官方支持城市（见 webservice 文档）
TRAFFIC_SUPPORTED_CITIES: Dict[str, Tuple[float, float]] = {
    "北京": (116.407526, 39.904030),
    "上海": (121.473701, 31.230416),
    "广州": (113.264385, 23.129112),
    "深圳": (114.057868, 22.543099),
    "宁波": (121.550357, 29.874557),
    "武汉": (114.305393, 30.593099),
    "重庆": (106.551556, 29.563009),
    "成都": (104.066541, 30.572269),
    "沈阳": (123.431475, 41.805698),
    "南京": (118.796877, 32.060255),
    "杭州": (120.155070, 30.274084),
    "长春": (125.323544, 43.817071),
    "常州": (119.946973, 31.772752),
    "大连": (121.614682, 38.914003),
    "东莞": (113.751799, 23.020673),
    "福州": (119.296494, 26.074507),
    "青岛": (120.382639, 36.067082),
    "石家庄": (114.514859, 38.042306),
    "天津": (117.200983, 39.084158),
    "太原": (112.548879, 37.870590),
    "西安": (108.940174, 34.341568),
    "无锡": (120.311910, 31.491169),
    "厦门": (118.089425, 24.479833),
    "珠海": (113.576726, 22.270715),
    "长沙": (112.938814, 28.228209),
    "苏州": (120.585315, 31.298886),
    "金华": (119.647444, 29.079059),
    "佛山": (113.121416, 23.021548),
    "济南": (117.120098, 36.651216),
    "泉州": (118.675676, 24.874132),
    "嘉兴": (120.755486, 30.746129),
    "西宁": (101.778228, 36.617134),
    "惠州": (114.415793, 23.111847),
    "温州": (120.699366, 27.994267),
    "中山": (113.392782, 22.517645),
    "合肥": (117.227239, 31.820586),
    "乌鲁木齐": (87.617733, 43.792818),
    "台州": (121.420757, 28.656386),
    "绍兴": (120.582112, 29.997117),
    "昆明": (102.832891, 24.880095),
}

# 未覆盖区域 → 参考城市（按省级 adcode 前两位）
PROVINCE_REFERENCE_CITY: Dict[str, str] = {
    "61": "西安",  # 陕西
    "62": "西安",  # 甘肃（距西宁/西安，选西安更常见）
    "64": "西安",  # 宁夏
}


def _parse_lnglat(location: str) -> List[float]:
    lng, lat = location.split(",", 1)[:2]
    return [float(lng), float(lat)]


def _format_location(location: str) -> str:
    lng, lat = _parse_lnglat(location.strip())
    return f"{lng:.6f},{lat:.6f}"


def _haversine_meters(a: List[float], b: List[float]) -> float:
    lng1, lat1 = a
    lng2, lat2 = b
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    x = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(x))


def _fetch_circle(location: str, radius: int, api_key: str) -> Dict[str, Any]:
    resp = requests.get(
        "https://restapi.amap.com/v3/traffic/status/circle",
        params={
            "key": api_key,
            "location": location,
            "radius": min(max(radius, 100), 5000),
            "output": "JSON",
        },
        timeout=15,
    )
    return resp.json()


def _regeo(location: str, api_key: str) -> Dict[str, Any]:
    try:
        resp = requests.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"key": api_key, "location": location, "output": "JSON"},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") != "1":
            return {}
        return data.get("regeocode", {}).get("addressComponent", {}) or {}
    except Exception:
        return {}


def _nearest_supported_city(lng: float, lat: float) -> Tuple[str, str]:
    origin = [lng, lat]
    best_name = "西安"
    best_dist = float("inf")
    for name, center in TRAFFIC_SUPPORTED_CITIES.items():
        dist = _haversine_meters(origin, list(center))
        if dist < best_dist:
            best_dist = dist
            best_name = name
    lng_c, lat_c = TRAFFIC_SUPPORTED_CITIES[best_name]
    return best_name, f"{lng_c:.6f},{lat_c:.6f}"


def _reference_city(adcode: str, lng: float, lat: float) -> Tuple[str, str]:
    prefix = (adcode or "")[:2]
    if prefix in PROVINCE_REFERENCE_CITY:
        name = PROVINCE_REFERENCE_CITY[prefix]
        if name in TRAFFIC_SUPPORTED_CITIES:
            lng_c, lat_c = TRAFFIC_SUPPORTED_CITIES[name]
            return name, f"{lng_c:.6f},{lat_c:.6f}"
    return _nearest_supported_city(lng, lat)


def _pct_label(value: Any) -> str:
    text = str(value if value not in (None, "") else "?").strip()
    if text.endswith("%"):
        return text
    return f"{text}%" if text != "?" else "?"


def _evaluation(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("trafficinfo", {}).get("evaluation", {}) or {}


def _build_traffic_map(
    *,
    center_location: str,
    center_name: str,
    radius: int,
    evaluation: Dict[str, Any],
    coverage_limited: bool = False,
    local_label: str = "",
    reference_city: str = "",
) -> Dict[str, Any]:
    desc = evaluation.get("description") or ("请查看地图路况图层" if coverage_limited else "暂无描述")
    try:
        lnglat = _parse_lnglat(center_location)
    except (ValueError, TypeError):
        lnglat = None

    payload: Dict[str, Any] = {
        "type": "traffic_map",
        "title": "周边实时路况" if not coverage_limited else "周边路况（地图图层）",
        "center": {
            "name": center_name,
            "location": center_location,
            "lnglat": lnglat,
        },
        "radius": radius,
        "status": desc,
        "expedite": evaluation.get("expedite", "?"),
        "congested": evaluation.get("congested", "?"),
        "blocked": evaluation.get("blocked", "?"),
    }
    if coverage_limited:
        payload["coverage_limited"] = True
        payload["local_area"] = local_label
        if reference_city:
            payload["reference_city"] = reference_city
    return payload


def query_traffic_status(
    location: str,
    radius: int = 1500,
    *,
    api_key: Optional[str] = None,
    center_name: str = "当前位置",
) -> Dict[str, Any]:
    """
    查询路况。若当前坐标不在 REST API 覆盖范围，仍返回 traffic_map（供前端加载路况图层），
    并附带最近支持城市的参考路况说明。
    """
    key = api_key or AMAP_API_KEY
    if not key:
        return {"error": "未配置高德地图API密钥"}

    try:
        formatted = _format_location(location)
        lng, lat = _parse_lnglat(formatted)
    except (ValueError, TypeError):
        return {"error": f"坐标格式无效：{location}"}

    data = _fetch_circle(formatted, radius, key)
    if data.get("status") == "1":
        evaluation = _evaluation(data)
        traffic_map = _build_traffic_map(
            center_location=formatted,
            center_name=center_name,
            radius=radius,
            evaluation=evaluation,
        )
        summary = (
            f"坐标 {formatted} 周边 {radius}米 路况：\n"
            f"{evaluation.get('description', '暂无描述')}\n"
            f"畅通路段占比: {_pct_label(evaluation.get('expedite', '?'))}，"
            f"缓行: {_pct_label(evaluation.get('congested', '?'))}，"
            f"拥堵: {_pct_label(evaluation.get('blocked', '?'))}"
        )
        return {"summary": summary, "traffic_map": traffic_map}

    regeo = _regeo(formatted, key)
    local_label = (
        (regeo.get("district") or "")
        or (regeo.get("city") or "")
        or (regeo.get("province") or "")
        or "当前区域"
    )
    adcode = str(regeo.get("adcode") or "")
    ref_city, ref_loc = _reference_city(adcode, lng, lat)

    ref_eval: Dict[str, Any] = {}
    ref_data = _fetch_circle(ref_loc, radius, key)
    if ref_data.get("status") == "1":
        ref_eval = _evaluation(ref_data)

    traffic_map = _build_traffic_map(
        center_location=formatted,
        center_name=center_name,
        radius=radius,
        evaluation={},
        coverage_limited=True,
        local_label=local_label,
        reference_city=ref_city,
    )

    lines = [
        f"{local_label}暂不支持高德「圆形区域路况统计」REST 接口（该接口仅覆盖部分重点城市）。",
        "已在地图上以您当前位置为中心加载实时路况图层，请直接查看红/黄/绿道路标识。",
    ]
    if ref_eval:
        lines.append(
            f"参考：距您最近的支持城市「{ref_city}」当前路况为 {ref_eval.get('description', '—')} "
            f"（畅通 {_pct_label(ref_eval.get('expedite', '?'))}，"
            f"缓行 {_pct_label(ref_eval.get('congested', '?'))}，"
            f"拥堵 {_pct_label(ref_eval.get('blocked', '?'))}），仅供区域出行参考。"
        )
    else:
        lines.append(f"您也可在高德地图 App 中打开实时路况图层查看 {local_label} 周边道路。")

    return {"summary": "\n".join(lines), "traffic_map": traffic_map}
