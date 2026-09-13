"""LangChain StructuredTool 封装 MCP 城市工具（按子 Agent 分派）"""
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool

from tools.mcp_client import call_mcp_tool


def _mcp(name: str, params: Dict[str, Any]) -> str:
    return call_mcp_tool(name, params)


def get_current_time() -> str:
    """获取当前本地时间、日期、星期"""
    return _mcp("get_current_time", {})


def get_current_weather(city: str) -> str:
    """获取指定城市的天气信息（请使用英文城市名）"""
    return _mcp("get_current_weather", {"city": city})


def get_city_poi(city: str, category: str = "sightseeing", page_size: int = 10) -> str:
    """获取指定城市的热门景点或餐饮推荐"""
    return _mcp("get_city_poi", {"city": city, "category": category, "page_size": page_size})


def get_city_weather_cn(city: str) -> str:
    """根据中文城市名获取中国国内城市天气预报"""
    return _mcp("get_city_weather_cn", {"city": city})


def amap_route_planning(
    origin: str,
    destination: str,
    mode: str = "driving",
    city: str = "",
) -> str:
    """规划路线，支持 driving/walking/transit/riding"""
    params: Dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
    }
    if city:
        params["city"] = city
    return _mcp("amap_route_planning", params)


def amap_geocode(keywords: str) -> str:
    """地名转经纬度坐标"""
    return _mcp("amap_geocode", {"keywords": keywords})


def amap_place_around(
    location: str,
    keywords: str = "",
    types: str = "",
    radius: int = 3000,
    page_size: int = 10,
) -> str:
    """根据坐标获取周边 POI 推荐"""
    return _mcp(
        "amap_place_around",
        {
            "location": location,
            "keywords": keywords,
            "types": types,
            "radius": radius,
            "page_size": page_size,
        },
    )


def amap_adcode_search(keywords: str) -> str:
    """地名转 adcode，用于天气预报"""
    return _mcp("amap_adcode_search", {"keywords": keywords})


def amap_weather_forecast(adcode: str) -> str:
    """根据 adcode 获取天气预报"""
    return _mcp("amap_weather_forecast", {"adcode": adcode})


def amap_ip_location(ip: str = "") -> str:
    """IP 定位城市与坐标"""
    params = {"ip": ip} if ip else {}
    return _mcp("amap_ip_location", params)


def amap_distance(origin: str, destination: str, distance_type: int = 1) -> str:
    """计算两点距离，type=1 直线 type=3 驾车"""
    return _mcp(
        "amap_distance",
        {"origin": origin, "destination": destination, "distance_type": distance_type},
    )


def amap_traffic_status(location: str, radius: int = 1500) -> str:
    """查询坐标周边实时路况"""
    return _mcp("amap_traffic_status", {"location": location, "radius": radius})


def plan_city_trip(city: str, days: int = 3, focus: str = "mixed") -> str:
    """生成城市旅游行程草案"""
    return _mcp("plan_city_trip", {"city": city, "days": days, "focus": focus})


def get_poi_detail(keywords: str, city: str = "", poi_id: str = "") -> str:
    """查询 POI 营业时间、门票与文化攻略"""
    params: Dict[str, Any] = {"keywords": keywords}
    if city:
        params["city"] = city
    if poi_id:
        params["poi_id"] = poi_id
    return _mcp("get_poi_detail", params)


def amap_transit_realtime(location: str, destination: str = "", city: str = "") -> str:
    """公交/地铁实时方案与附近站点"""
    params: Dict[str, Any] = {"location": location}
    if destination:
        params["destination"] = destination
    if city:
        params["city"] = city
    return _mcp("amap_transit_realtime", params)


def amap_regeocode(location: str) -> str:
    """逆地理编码：坐标转地址"""
    return _mcp("amap_regeocode", {"location": location})


def tts_speak(text: str) -> str:
    """文字转语音"""
    return _mcp("tts_speak", {"text": text})


def analyze_scene_image(
    scene_description: str,
    location: str = "",
    keywords: str = "景点",
) -> str:
    """结合场景描述与坐标搜索周边 POI 并解读"""
    return _mcp(
        "analyze_scene_image",
        {
            "scene_description": scene_description,
            "location": location,
            "keywords": keywords,
        },
    )


def generate_poi_visual(poi_name: str, style: str = "实景照片") -> str:
    """生成 POI 效果图（需用户确认）"""
    return _mcp("generate_poi_visual", {"poi_name": poi_name, "style": style})


def amap_transit_nearby(location: str, radius: int = 1500) -> str:
    """查询附近地铁/公交站"""
    return _mcp("amap_transit_nearby", {"location": location, "radius": radius})


def amap_schema_navi(
    location: str,
    mode: str = "car",
    from_lon: str = "",
    from_lat: str = "",
    from_name: str = "起点",
    to_name: str = "终点",
) -> str:
    """生成唤起高德 App 导航的 URI"""
    return _mcp(
        "amap_schema_navi",
        {
            "location": location,
            "mode": mode,
            "from_lon": from_lon,
            "from_lat": from_lat,
            "from_name": from_name,
            "to_name": to_name,
        },
    )


def amap_schema_taxi(lon: str, lat: str, name: str = "目的地") -> str:
    """生成唤起高德 App 叫车的 URI"""
    return _mcp("amap_schema_taxi", {"lon": lon, "lat": lat, "name": name})


def emergency_nearest_hospital(location: str) -> str:
    """查找最近医院并规划路线"""
    return _mcp("emergency_nearest_hospital", {"location": location})


ALL_TOOL_FUNCS = [
    get_current_time,
    get_current_weather,
    get_city_poi,
    get_city_weather_cn,
    amap_route_planning,
    amap_geocode,
    amap_place_around,
    amap_adcode_search,
    amap_weather_forecast,
    amap_ip_location,
    amap_distance,
    amap_traffic_status,
    plan_city_trip,
    get_poi_detail,
    amap_transit_realtime,
    amap_regeocode,
    tts_speak,
    analyze_scene_image,
    generate_poi_visual,
    amap_transit_nearby,
    amap_schema_navi,
    amap_schema_taxi,
    emergency_nearest_hospital,
]

ALL_TOOLS: List[StructuredTool] = [StructuredTool.from_function(f) for f in ALL_TOOL_FUNCS]

NAVIGATOR_TOOL_NAMES = {
    "amap_route_planning",
    "amap_transit_realtime",
    "amap_schema_navi",
    "amap_schema_taxi",
    "amap_distance",
    "amap_geocode",
    "get_current_time",
}

LOCAL_SCOUT_TOOL_NAMES = {
    "amap_place_around",
    "amap_transit_nearby",
    "amap_regeocode",
    "amap_distance",
    "get_current_time",
}

CITY_GUIDE_TOOL_NAMES = {
    "get_city_poi",
    "get_poi_detail",
    "get_city_weather_cn",
    "amap_adcode_search",
    "amap_weather_forecast",
    "amap_geocode",
    "amap_ip_location",
    "get_current_time",
}

CREATIVE_TOOL_NAMES = {
    "generate_poi_visual",
    "analyze_scene_image",
    "tts_speak",
    "get_current_time",
}

TRIP_TOOL_NAMES = {
    "plan_city_trip",
    "get_city_poi",
    "get_city_weather_cn",
    "get_current_time",
    "get_poi_detail",
}

GUARD_TOOL_NAMES = {
    "amap_traffic_status",
    "emergency_nearest_hospital",
    "amap_route_planning",
    "amap_schema_navi",
    "amap_regeocode",
    "amap_transit_realtime",
    "get_current_time",
}

COMPANION_TOOL_NAMES = {
    "get_current_time",
    "get_city_weather_cn",
    "amap_ip_location",
}

_TOOL_MAP = {t.name: t for t in ALL_TOOLS}

_AGENT_TOOL_NAMES = {
    "navigator": NAVIGATOR_TOOL_NAMES,
    "local_scout": LOCAL_SCOUT_TOOL_NAMES,
    "city_guide": CITY_GUIDE_TOOL_NAMES,
    "creative": CREATIVE_TOOL_NAMES,
    "trip_planner": TRIP_TOOL_NAMES,
    "realtime_guard": GUARD_TOOL_NAMES,
    "companion": COMPANION_TOOL_NAMES,
    "general": CITY_GUIDE_TOOL_NAMES,
}

NAVIGATOR_TOOLS = [t for t in ALL_TOOLS if t.name in NAVIGATOR_TOOL_NAMES]
LOCAL_SCOUT_TOOLS = [t for t in ALL_TOOLS if t.name in LOCAL_SCOUT_TOOL_NAMES]
CITY_GUIDE_TOOLS = [t for t in ALL_TOOLS if t.name in CITY_GUIDE_TOOL_NAMES]
CREATIVE_TOOLS = [t for t in ALL_TOOLS if t.name in CREATIVE_TOOL_NAMES]
TRIP_TOOLS = [t for t in ALL_TOOLS if t.name in TRIP_TOOL_NAMES]
GUARD_TOOLS = [t for t in ALL_TOOLS if t.name in GUARD_TOOL_NAMES]
COMPANION_TOOLS = [t for t in ALL_TOOLS if t.name in COMPANION_TOOL_NAMES]

_AGENT_TOOLS = {
    "navigator": NAVIGATOR_TOOLS,
    "local_scout": LOCAL_SCOUT_TOOLS,
    "city_guide": CITY_GUIDE_TOOLS,
    "creative": CREATIVE_TOOLS,
    "trip_planner": TRIP_TOOLS,
    "realtime_guard": GUARD_TOOLS,
    "companion": COMPANION_TOOLS,
    "general": CITY_GUIDE_TOOLS,
}


def get_tools_for_agent(agent_type: str) -> List[StructuredTool]:
    from graph.agents import normalize_agent_name

    key = normalize_agent_name(agent_type)
    return _AGENT_TOOLS.get(key, CITY_GUIDE_TOOLS)


def get_tool_by_name(name: str) -> Optional[StructuredTool]:
    return _TOOL_MAP.get(name)


def tool_names_for_agent(agent_type: str) -> frozenset:
    from graph.agents import normalize_agent_name

    return frozenset(_AGENT_TOOL_NAMES.get(normalize_agent_name(agent_type), CITY_GUIDE_TOOL_NAMES))
