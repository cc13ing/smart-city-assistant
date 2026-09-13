# mcp_server.py
from fast_mcp import FastMCP, text_response, create_fastapi_app
import uvicorn
from datetime import datetime
import time # 用于 get_current_time
import requests
import os
import json
import re
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Union
import asyncio
import json
from fastapi import BackgroundTasks, Response
from dotenv import load_dotenv
# 加载 .env 文件中的环境变量
load_dotenv()

async def sse_response(generator: Union[Generator[str, None, None], AsyncGenerator[str, None]]) -> Response:
    """将生成器转换为SSE响应"""
    async def stream_generator():
        if asyncio.iscoroutinefunction(generator.__anext__):
            # 异步生成器
            async for data in generator:
                yield f"data: {data}\n\n"
        else:
            # 同步生成器
            for data in generator:
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)

    return Response(
        content=stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )

# 1. 创建 FastMCP 服务实例
# FastMCP 是一个轻量级的 MCP 服务器实现
utility_mcp = FastMCP(
    name="My MCP Tools",
    description="一些常用的实用工具集合",
    version="1.0.0"
)

# 2. 获取当前时间
@utility_mcp.tool(
    name="get_current_time",
    description="获取当前的日期和时间信息"
)
def get_current_time_tool(): # 注意：工具函数名可以和工具名不同
    """
    获取当前的日期和时间。
    Returns:
        包含当前日期和时间的文本响应。
    """
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    response = (
        f"当前日期: {now.strftime('%Y-%m-%d')}\n"
        f"当前时间: {now.strftime('%H:%M:%S')}\n"
        f"星期: {weekdays[now.weekday()]}"
    )
    return text_response(response)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@utility_mcp.tool(
    name="get_current_weather",
    description="获取当前的天气信息，需要提供城市名称"
)
def get_current_weather_tool(city: str):
    try:
        # 请求 OpenWeatherMap API
        url = f"http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric",
            "lang": "zh_cn"
        }
        response = requests.get(url, params=params)
        data = response.json()

        if response.status_code != 200:
            return text_response(f"获取{city}天气失败：{data.get('message', '未知错误')}")

        weather_desc = data['weather'][0]['description']
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        return text_response(f"{city}当前天气是 {weather_desc}，温度为 {temp}°C，体感温度为 {feels_like}°C")
    
    except Exception as e:
        return text_response(f"获取{city}天气时出错：{str(e)}")

# 高德地图API工具
AMAP_API_KEY = os.getenv("AMAP_API_KEY")

def _is_coordinate(text: str) -> bool:
    """判断字符串是否为 '经度,纬度' 格式"""
    return bool(re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*$", text.strip()))

def _resolve_location(keywords: str, city: str = "", near: str = "") -> dict:
    """将地名或地址解析为经纬度坐标，返回 {location, name, citycode}。"""
    from services.geocode import resolve_place
    from services.route_destination import should_bias_geocode_to_near

    if not AMAP_API_KEY:
        return {"error": "未配置高德地图API密钥"}
    if _is_coordinate(keywords):
        return {"location": keywords.strip(), "name": keywords.strip(), "citycode": ""}

    bias_near = near if should_bias_geocode_to_near(keywords) else ""
    result = resolve_place(keywords, city, bias_near)
    if "error" in result:
        return {"error": result["error"]}
    return {
        "location": result.get("location", ""),
        "name": result.get("name", keywords),
        "citycode": "",
        "adcode": "",
    }

def _format_duration(seconds) -> str:
    """将秒数格式化为可读时长"""
    try:
        sec = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    if sec < 60:
        return f"{sec}秒"
    minutes, sec = divmod(sec, 60)
    if minutes < 60:
        return f"{minutes}分钟{sec}秒" if sec else f"{minutes}分钟"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}小时{minutes}分钟"

def _parse_route_steps(steps, max_steps: int = 8) -> list:
    """提取路线分段指示"""
    instructions = []
    for step in steps[:max_steps]:
        instruction = step.get("instruction") or step.get("instruction", "")
        road = step.get("road_name") or step.get("road", "")
        dist = step.get("step_distance") or step.get("distance", "")
        if instruction:
            line = instruction
            if road and road not in instruction:
                line += f"（{road}）"
            if dist:
                line += f"，{dist}米"
            instructions.append(line)
    if len(steps) > max_steps:
        instructions.append(f"... 还有 {len(steps) - max_steps} 个路段")
    return instructions


def _parse_lnglat(loc_str: str) -> List[float]:
    """将 '经度,纬度' 解析为 [lng, lat]"""
    parts = [p.strip() for p in str(loc_str).split(",")]
    if len(parts) < 2:
        raise ValueError(f"无效坐标: {loc_str}")
    return [float(parts[0]), float(parts[1])]


def _haversine_meters(a: List[float], b: List[float]) -> float:
    import math

    lng1, lat1 = a
    lng2, lat2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def _merge_step_polylines(steps) -> List[List[float]]:
    """合并各路段 polyline 为完整路径坐标"""
    coords: List[List[float]] = []
    for step in steps or []:
        polyline = step.get("polyline") or ""
        for point in polyline.split(";"):
            point = point.strip()
            if not point or "," not in point:
                continue
            lng, lat = point.split(",", 1)
            pair = [float(lng), float(lat)]
            if not coords or coords[-1] != pair:
                coords.append(pair)
    return coords


def _fetch_route_path_v3(
    origin_loc: str, dest_loc: str, mode: str = "driving"
) -> List[List[float]]:
    """v5 无 polyline 时回退 v3 接口（steps 自带 polyline）"""
    v3_urls = {
        "driving": "https://restapi.amap.com/v3/direction/driving",
        "walking": "https://restapi.amap.com/v3/direction/walking",
        "riding": "https://restapi.amap.com/v3/direction/bicycling",
    }
    url = v3_urls.get(mode)
    if not url or not AMAP_API_KEY:
        return []
    params = {
        "key": AMAP_API_KEY,
        "origin": origin_loc,
        "destination": dest_loc,
        "extensions": "all",
        "output": "JSON",
    }
    if mode == "driving":
        params["strategy"] = 0
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != "1":
            return []
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            return []
        steps = paths[0].get("steps") or []
        return _merge_step_polylines(steps)
    except Exception:
        return []


@utility_mcp.tool(
    name="amap_geocode",
    description="根据关键字搜索（如“苏州中心”）获取经纬度坐标，适用于后续中心点为圆心周边半径的推荐。"
)
def amap_geocode_tool(
    keywords: str,
):
    """
    使用高德地图place/text接口获取地名或地址的经纬度坐标。
    Args:
        keywords: 地点名称或地址（如“苏州中心”）
    Returns:
        经纬度坐标字符串，如 '120.677934,31.316626'
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    url = "https://restapi.amap.com/v5/place/text"
    params = {
        "key": AMAP_API_KEY,
        "keywords": keywords,
        "page_size": 1,
        "output": "JSON"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response(f"未找到地点，原因：{data.get('info', '未知错误')}")
        pois = data["pois"]
        location = pois[0].get("location", "")
        name = pois[0].get("name", "")
        address = pois[0].get("address", "")
        if location:
            return text_response(f"{name}（{address}）的坐标为：{location}")
        else:
            return text_response("未获取到坐标信息")
    except Exception as e:
        return text_response(f"获取经纬度坐标时出错：{str(e)}")

@utility_mcp.tool(
    name="amap_place_around",
    description="根据经纬度坐标获取周边推荐POI（如餐饮、景点、商场等），支持自定义类型和半径，可以返回https://www.amap.com/place/<id>的链接"
)
def amap_place_around_tool(
    location: str,  # 格式：'经度,纬度'
    types: str = "",
    radius: int = 1000,
    keywords: str = "",
    page_size: int = 10
):
    """
    使用高德地图place/around接口获取指定坐标周边的POI推荐。
    Args:
        location: 中心点坐标，格式'经度,纬度'
        types: POI类型（可选），如'餐饮服务;风景名胜;购物服务'，多个类型用分号分隔
        radius: 搜索半径（米），默认1000米
        keywords: 关键词（可选）
        page_size: 返回结果数量，最大25, 默认为10
    Returns:
        周边POI推荐列表
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    url = "https://restapi.amap.com/v5/place/around"
    params = {
        "key": AMAP_API_KEY,
        "location": location,
        "types": types,
        "radius": radius,
        "keywords": keywords,
        "page_size": page_size,
        "output": "JSON"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response(f"未找到周边推荐，原因：{data.get('info', '未知错误')}")
        pois = data["pois"]
        result = []
        poi_items = []
        for poi in pois:
            name = poi.get("name", "")
            address = poi.get("address", "")
            poi_type = poi.get("type", "")
            distance = poi.get("distance", "")
            poi_id = poi.get("id", "")
            amap_url = f"https://www.amap.com/place/{poi_id}" if poi_id else ""
            result.append(f"{name}（类型：{poi_type}，地址：{address}，距离：{distance}米，id：{poi_id}{'，链接：' + amap_url if amap_url else ''}）")
            loc = poi.get("location", "")
            if loc and "," in loc:
                try:
                    poi_items.append(
                        {
                            "name": name,
                            "address": address,
                            "type": poi_type,
                            "distance": distance,
                            "location": loc,
                            "lnglat": _parse_lnglat(loc),
                            "poi_id": poi_id,
                            "id": poi_id,
                        }
                    )
                except (ValueError, TypeError):
                    pass
        summary = "\n".join(result)
        if poi_items:
            try:
                center_lnglat = _parse_lnglat(location)
            except (ValueError, TypeError):
                center_lnglat = poi_items[0]["lnglat"]
            payload = {
                "summary": summary,
                "poi_map": {
                    "type": "poi_map",
                    "title": "周边推荐",
                    "center": {
                        "name": "当前位置",
                        "location": location,
                        "lnglat": center_lnglat,
                    },
                    "pois": poi_items[:8],
                },
            }
            return text_response(json.dumps(payload, ensure_ascii=False))
        return text_response(summary)
    except Exception as e:
        return text_response(f"获取周边推荐时出错：{str(e)}")


@utility_mcp.tool(
    name="amap_adcode_search",
    description="根据地名或地址获取高德地图adcode城市/区县代码，适用于后续天气预报等场景。"
)
def amap_adcode_search_tool(
    keywords: str,
):
    """
    使用高德地图place/text接口获取地名或地址的adcode。
    Args:
        keywords: 地点名称或地址（如“西安”）
        city: 城市名称（可选）
    Returns:
        adcode字符串，如 '610112'
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    url = "https://restapi.amap.com/v5/place/text"
    params = {
        "key": AMAP_API_KEY,
        "keywords": keywords,
        "page_size": 1,
        "output": "JSON"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response(f"未找到地点，原因：{data.get('info', '未知错误')}")
        pois = data["pois"]
        adcode = pois[0].get("adcode", "")
        name = pois[0].get("name", "")
        address = pois[0].get("address", "")
        if adcode:
            return text_response(f"{name}（{address}）的adcode为：{adcode}")
        else:
            return text_response("未获取到adcode信息")
    except Exception as e:
        return text_response(f"获取adcode时出错：{str(e)}")

@utility_mcp.tool(
    name="amap_weather_forecast",
    description="根据adcode获取中国国内城市或区县的天气预报（含未来几天天气），需先通过amap_adcode_search获取adcode。"
)
def amap_weather_forecast_tool(
    adcode: str
):
    """
    使用高德地图weather/weatherInfo接口获取天气预报。
    Args:
        adcode: 城市或区县adcode代码
    Returns:
        天气预报信息
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {
        "key": AMAP_API_KEY,
        "city": adcode,
        "extensions": "all",
        "output": "JSON"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("status") != "1" or not data.get("forecasts"):
            return text_response(f"未找到天气预报，原因：{data.get('info', '未知错误')}")
        forecast = data["forecasts"][0]
        city = forecast.get("city", "")
        province = forecast.get("province", "")
        reporttime = forecast.get("reporttime", "")
        casts = forecast.get("casts", [])
        result = [f"{province}{city}（adcode: {adcode}）天气预报，发布时间：{reporttime}"]
        for cast in casts:
            date = cast.get("date", "")
            week = cast.get("week", "")
            dayweather = cast.get("dayweather", "")
            nightweather = cast.get("nightweather", "")
            daytemp = cast.get("daytemp", "")
            nighttemp = cast.get("nighttemp", "")
            daywind = cast.get("daywind", "")
            nightwind = cast.get("nightwind", "")
            daypower = cast.get("daypower", "")
            nightpower = cast.get("nightpower", "")
            result.append(f"{date}（周{week}）：白天{dayweather}，夜间{nightweather}，最高{daytemp}℃，最低{nighttemp}℃，白天风向{daywind}{daypower}级，夜间风向{nightwind}{nightpower}级")
        return text_response("\n".join(result))
    except Exception as e:
        return text_response(f"获取天气预报时出错：{str(e)}")


@utility_mcp.tool(
    name="amap_route_planning",
    description="使用高德地图API规划从起点到终点的路线，支持驾车(driving)、步行(walking)、公交(transit)、骑行(riding)等出行方式"
)
def amap_route_planning_tool(
    origin: str,
    destination: str,
    mode: str = "driving",
    city: str = "",
):
    """
    规划两点之间的出行路线。
    Args:
        origin: 起点地址、地名或坐标（经度,纬度）
        destination: 终点地址、地名或坐标
        mode: 出行方式 driving/walking/transit/riding
        city: 城市名称，公交规划时建议提供
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")

    origin_info = _resolve_location(origin, city)
    if "error" in origin_info:
        return text_response(f"起点解析失败：{origin_info['error']}")
    dest_info = _resolve_location(destination, city, near=origin_info["location"])
    if "error" in dest_info:
        return text_response(f"终点解析失败：{dest_info['error']}")

    origin_loc = origin_info["location"]
    dest_loc = dest_info["location"]
    origin_name = origin_info["name"]
    dest_name = dest_info["name"]

    mode_map = {
        "driving": ("驾车", "https://restapi.amap.com/v5/direction/driving"),
        "walking": ("步行", "https://restapi.amap.com/v5/direction/walking"),
        "riding": ("骑行", "https://restapi.amap.com/v5/direction/bicycling"),
    }

    try:
        if mode == "transit":
            transit_city = city or origin_info.get("adcode", "") or dest_info.get("adcode", "")
            if not transit_city:
                return text_response("公交路线规划需要提供 city 参数（如：北京、上海）")
            url = "https://restapi.amap.com/v3/direction/transit/integrated"
            params = {
                "key": AMAP_API_KEY,
                "origin": origin_loc,
                "destination": dest_loc,
                "city": transit_city,
                "output": "JSON",
            }
            response = requests.get(url, params=params, timeout=15)
            data = response.json()
            if data.get("status") != "1" or not data.get("route", {}).get("transits"):
                return text_response(f"未找到公交路线，原因：{data.get('info', '未知错误')}")

            transit = data["route"]["transits"][0]
            distance = transit.get("duration", "")
            cost = transit.get("cost", "")
            walking_distance = transit.get("walking_distance", "")
            segments = transit.get("segments", [])
            seg_lines = []
            for seg in segments[:10]:
                if seg.get("bus", {}).get("buslines"):
                    busline = seg["bus"]["buslines"][0]
                    seg_lines.append(f"乘坐 {busline.get('name', '公交')}，{busline.get('via_num', 0)}站")
                elif seg.get("walking"):
                    walk = seg["walking"]
                    seg_lines.append(f"步行 {walk.get('distance', '?')}米，约{_format_duration(walk.get('duration', 0))}")

            result = [
                f"公交路线：{origin_name} → {dest_name}",
                f"预计耗时：{_format_duration(distance)}",
            ]
            if cost:
                result.append(f"预计费用：{cost}元")
            if walking_distance:
                result.append(f"步行距离：{walking_distance}米")
            result.append("换乘方案：")
            result.extend(seg_lines or ["暂无详细分段信息"])
            return text_response("\n".join(result))

        if mode not in mode_map:
            return text_response(f"不支持的出行方式：{mode}，可选：driving/walking/transit/riding")

        mode_label, url = mode_map[mode]
        params = {
            "key": AMAP_API_KEY,
            "origin": origin_loc,
            "destination": dest_loc,
            # 必须包含 polyline，否则 steps 无坐标，地图只能画直线
            "show_fields": "polyline,cost",
            "output": "JSON",
        }
        if mode == "driving":
            params["strategy"] = 32

        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get("status") != "1":
            return text_response(f"路线规划失败，原因：{data.get('info', '未知错误')}")

        route = data.get("route", {})
        paths = route.get("paths") or route.get("path") or []
        if isinstance(paths, dict):
            paths = [paths]
        if not paths:
            return text_response(f"未找到{mode_label}路线")

        path = paths[0]
        distance = path.get("distance", "?")
        duration = path.get("duration") or path.get("cost", {}).get("duration", "?")
        steps = path.get("steps", [])
        instructions = _parse_route_steps(steps)
        route_path = _merge_step_polylines(steps)
        if not route_path:
            top_polyline = path.get("polyline") or ""
            route_path = _merge_step_polylines([{"polyline": top_polyline}])
        if len(route_path) < 3:
            route_path = _fetch_route_path_v3(origin_loc, dest_loc, mode)
        path_fallback = False
        if len(route_path) < 3:
            route_path = [_parse_lnglat(origin_loc), _parse_lnglat(dest_loc)]
            path_fallback = True

        summary_lines = [
            f"{mode_label}路线：{origin_name} → {dest_name}",
            f"总距离：{distance}米",
            f"预计耗时：{_format_duration(duration)}",
            "主要路段：",
        ]
        summary_lines.extend(instructions or ["暂无详细路段信息"])

        payload = {
            "type": "route",
            "mode": mode,
            "mode_label": mode_label,
            "origin": {
                "name": origin_name,
                "location": origin_loc,
                "lnglat": _parse_lnglat(origin_loc),
            },
            "destination": {
                "name": dest_name,
                "location": dest_loc,
                "lnglat": _parse_lnglat(dest_loc),
            },
            "distance": int(distance) if str(distance).isdigit() else distance,
            "duration": int(duration) if str(duration).isdigit() else duration,
            "duration_text": _format_duration(duration),
            "path": route_path,
            "path_fallback": path_fallback,
            "summary": "\n".join(summary_lines),
        }
        from services.amap_uri import attach_navi_uri

        attach_navi_uri(payload)
        return text_response(json.dumps(payload, ensure_ascii=False))

    except Exception as e:
        return text_response(f"路线规划时出错：{str(e)}")


@utility_mcp.tool(
    name="get_city_poi",
    description="获取指定城市的热门景点或餐饮推荐，支持中文城市名"
)
def get_city_poi_tool(
    city: str,
    category: str = "sightseeing",
    page_size: int = 10,
):
    """
    搜索城市内的热门 POI。
    Args:
        city: 城市名称（中文或英文），如 北京、上海、Tokyo
        category: sightseeing(景点) 或 food(美食)
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")

    category_config = {
        "sightseeing": {"keywords": "景点", "types": "110000", "label": "景点"},
        "food": {"keywords": "美食", "types": "050000", "label": "餐饮"},
    }
    if category not in category_config:
        return text_response(f"不支持的类别：{category}，可选：sightseeing、food")

    cfg = category_config[category]
    url = "https://restapi.amap.com/v5/place/text"
    params = {
        "key": AMAP_API_KEY,
        "keywords": cfg["keywords"],
        "types": cfg["types"],
        "city": city,
        "page_size": min(page_size, 25),
        "output": "JSON",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response(f"未找到{city}的{cfg['label']}推荐，原因：{data.get('info', '未知错误')}")

        result = [f"{city}热门{cfg['label']}推荐："]
        poi_items = []
        for poi in data["pois"]:
            name = poi.get("name", "")
            address = poi.get("address", "")
            poi_type = poi.get("type", "")
            poi_id = poi.get("id", "")
            amap_url = f"https://www.amap.com/place/{poi_id}" if poi_id else ""
            line = f"- {name}（{poi_type}，地址：{address}"
            if amap_url:
                line += f"，链接：{amap_url}"
            line += "）"
            result.append(line)
            loc = poi.get("location", "")
            if loc and "," in loc:
                try:
                    poi_items.append(
                        {
                            "name": name,
                            "address": address,
                            "type": poi_type,
                            "location": loc,
                            "lnglat": _parse_lnglat(loc),
                            "poi_id": poi_id,
                            "id": poi_id,
                        }
                    )
                except (ValueError, TypeError):
                    pass
        summary = "\n".join(result)
        if poi_items:
            resolved = _resolve_location(city)
            if resolved.get("location"):
                center_lnglat = _parse_lnglat(resolved["location"])
                center_name = resolved.get("name", city)
                center_loc = resolved["location"]
            else:
                center_lnglat = poi_items[0]["lnglat"]
                center_name = city
                center_loc = poi_items[0]["location"]
            label = cfg["label"]
            payload = {
                "summary": summary,
                "poi_map": {
                    "type": "poi_map",
                    "scope": "city",
                    "show_path": False,
                    "title": f"{city}{label}推荐",
                    "center": {
                        "name": center_name,
                        "location": center_loc,
                        "lnglat": center_lnglat,
                    },
                    "pois": poi_items[:8],
                },
            }
            return text_response(json.dumps(payload, ensure_ascii=False))
        return text_response(summary)
    except Exception as e:
        return text_response(f"获取{city} POI推荐时出错：{str(e)}")


@utility_mcp.tool(
    name="get_city_weather_cn",
    description="根据中文城市名获取中国国内城市的天气预报（含未来几天），一步完成 adcode 查询和天气获取"
)
def get_city_weather_cn_tool(city: str):
    """
    统一的中文城市天气查询。
    Args:
        city: 中文城市名，如 北京、深圳、西安
    """
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")

    adcode_result = _resolve_location(city)
    if "error" in adcode_result:
        return text_response(adcode_result["error"])

    adcode = adcode_result.get("adcode", "")
    if not adcode:
        return text_response(f"未能获取「{city}」的 adcode")

    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {
        "key": AMAP_API_KEY,
        "city": adcode,
        "extensions": "all",
        "output": "JSON",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") != "1" or not data.get("forecasts"):
            return text_response(f"未找到{city}天气预报，原因：{data.get('info', '未知错误')}")

        forecast = data["forecasts"][0]
        city_name = forecast.get("city", city)
        province = forecast.get("province", "")
        reporttime = forecast.get("reporttime", "")
        casts = forecast.get("casts", [])

        result = [f"{province}{city_name}天气预报（发布时间：{reporttime}）"]
        for cast in casts:
            date = cast.get("date", "")
            week = cast.get("week", "")
            dayweather = cast.get("dayweather", "")
            nightweather = cast.get("nightweather", "")
            daytemp = cast.get("daytemp", "")
            nighttemp = cast.get("nighttemp", "")
            result.append(
                f"{date}（周{week}）：白天{dayweather}，夜间{nightweather}，"
                f"{nighttemp}~{daytemp}℃"
            )
        return text_response("\n".join(result))
    except Exception as e:
        return text_response(f"获取{city}天气时出错：{str(e)}")


@utility_mcp.tool(
    name="amap_regeocode",
    description="根据经纬度坐标反查地址、城市、区县，用于将用户 GPS 坐标转换为可读位置。"
)
def amap_regeocode_tool(location: str):
    """坐标转地址（逆地理编码）"""
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    if not _is_coordinate(location):
        return text_response("location 须为 经度,纬度 格式")
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "key": AMAP_API_KEY,
        "location": location.strip(),
        "extensions": "base",
        "output": "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1":
            return text_response(f"逆地理编码失败：{data.get('info', '未知错误')}")
        regeo = data.get("regeocode", {})
        addr = regeo.get("formatted_address", "")
        comp = regeo.get("addressComponent", {})
        province = comp.get("province", "")
        city = comp.get("city") or comp.get("province", "")
        district = comp.get("district", "")
        township = comp.get("township", "")
        return text_response(
            f"坐标：{location}\n"
            f"地址：{addr}\n"
            f"省份：{province}\n"
            f"城市：{city}\n"
            f"区县：{district}\n"
            f"街道：{township}"
        )
    except Exception as e:
        return text_response(f"逆地理编码出错：{str(e)}")


@utility_mcp.tool(
    name="amap_ip_location",
    description="根据 IP 地址定位所在城市与大致坐标；不传 ip 则定位服务器出口 IP。用于「我在哪」「附近推荐」等场景。"
)
def amap_ip_location_tool(ip: str = ""):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    url = "https://restapi.amap.com/v3/ip"
    params = {"key": AMAP_API_KEY, "output": "JSON"}
    if ip:
        params["ip"] = ip
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1":
            return text_response(f"IP 定位失败：{data.get('info', '未知错误')}")
        rectangle = data.get("rectangle", "")
        loc = ""
        if rectangle and ";" in rectangle:
            pts = rectangle.split(";")
            if len(pts) == 2:
                lng1, lat1 = pts[0].split(",")
                lng2, lat2 = pts[1].split(",")
                loc = f"{(float(lng1) + float(lng2)) / 2:.6f},{(float(lat1) + float(lat2)) / 2:.6f}"
        return text_response(
            f"IP: {ip or '当前'}\n"
            f"省份: {data.get('province', '')}\n"
            f"城市: {data.get('city', '')}\n"
            f"adcode: {data.get('adcode', '')}\n"
            f"矩形范围: {rectangle}\n"
            f"建议中心坐标: {loc or '未知'}"
        )
    except Exception as e:
        return text_response(f"IP 定位出错：{str(e)}")


@utility_mcp.tool(
    name="amap_distance",
    description="计算两点间距离。type=1 直线距离，type=3 驾车导航距离（米）。"
)
def amap_distance_tool(
    origin: str,
    destination: str,
    distance_type: int = 1,
):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    o = _resolve_location(origin)
    if "error" in o:
        return text_response(f"起点解析失败：{o['error']}")
    d = _resolve_location(destination)
    if "error" in d:
        return text_response(f"终点解析失败：{d['error']}")
    url = "https://restapi.amap.com/v3/distance"
    params = {
        "key": AMAP_API_KEY,
        "origins": o["location"],
        "destination": d["location"],
        "type": distance_type,
        "output": "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != "1" or not data.get("results"):
            return text_response(f"距离计算失败：{data.get('info', '未知错误')}")
        r = data["results"][0]
        dist = int(r.get("distance", 0))
        dur = r.get("duration", "")
        type_label = "直线" if distance_type == 1 else "驾车"
        km = dist / 1000
        text = f"{o['name']} → {d['name']}\n{type_label}距离：{dist}米（约{km:.1f}公里）"
        if dur:
            text += f"\n预计驾车时长：{_format_duration(dur)}"
        return text_response(text)
    except Exception as e:
        return text_response(f"距离计算出错：{str(e)}")


@utility_mcp.tool(
    name="amap_traffic_status",
    description="查询指定坐标周边实时路况（畅通/缓行/拥堵等）。"
)
def amap_traffic_status_tool(location: str, radius: int = 1500):
    if not _is_coordinate(location):
        resolved = _resolve_location(location)
        if "error" in resolved:
            return text_response(resolved["error"])
        location = resolved["location"]
    from services.traffic_status import query_traffic_status

    result = query_traffic_status(location, radius)
    if "error" in result:
        return text_response(result["error"])
    return text_response(json.dumps(result, ensure_ascii=False))


@utility_mcp.tool(
    name="get_poi_detail",
    description="查询 POI 详情：营业时间、门票、评分、地址，并附文化攻略",
)
def get_poi_detail_tool(keywords: str, city: str = "", poi_id: str = "", hint_location: str = ""):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    from services.poi_guide import enrich_poi_detail
    from services.route_destination import _normalize_poi_name

    keywords = _normalize_poi_name(keywords)
    poi_raw: Optional[dict] = None
    try:
        if poi_id:
            resp = requests.get(
                "https://restapi.amap.com/v3/place/detail",
                params={"key": AMAP_API_KEY, "id": poi_id, "output": "JSON"},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("pois"):
                poi_raw = data["pois"][0]
        if not poi_raw and keywords:
            params: Dict[str, Any] = {
                "key": AMAP_API_KEY,
                "keywords": keywords,
                "page_size": 10 if hint_location else 1,
                "output": "JSON",
            }
            if city:
                params["city"] = city
                params["citylimit"] = "true"
            resp = requests.get(
                "https://restapi.amap.com/v5/place/text",
                params=params,
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("pois"):
                pois = data["pois"]
                if hint_location and _is_coordinate(hint_location) and len(pois) > 1:
                    try:
                        origin_ll = _parse_lnglat(hint_location)

                        def _dist(p):
                            loc = p.get("location", "")
                            if not loc:
                                return float("inf")
                            return _haversine_meters(origin_ll, _parse_lnglat(loc))

                        poi_raw = min(pois, key=_dist)
                    except (ValueError, TypeError):
                        poi_raw = pois[0]
                else:
                    poi_raw = pois[0]
    except Exception as e:
        return text_response(f"POI 详情查询失败：{e}")

    if not poi_raw:
        detail = enrich_poi_detail({"name": keywords, "type": "unknown"})
        payload = {"type": "poi_detail", "poi": detail, "summary": f"未找到「{keywords}」的高德详情，仅提供攻略摘要。"}
        return text_response(json.dumps(payload, ensure_ascii=False))

    biz = poi_raw.get("biz_ext") or {}
    detail = enrich_poi_detail(
        {
            "name": poi_raw.get("name", keywords),
            "poi_id": poi_raw.get("id", poi_id),
            "address": poi_raw.get("address") or poi_raw.get("cityname", ""),
            "location": poi_raw.get("location", ""),
            "type": poi_raw.get("type", ""),
            "tel": poi_raw.get("tel") or poi_raw.get("business", {}).get("tel", ""),
            "rating": biz.get("rating") or poi_raw.get("rating", ""),
            "cost": biz.get("cost", ""),
            "opentime": biz.get("open_time") or poi_raw.get("opentime", "") or "以现场公告为准",
            "ticket": biz.get("ticket", "") or "请查询官方渠道",
        }
    )
    summary = (
        f"{detail['name']}：{detail.get('address', '')}；"
        f"营业/开放：{detail.get('opentime', '—')}；"
        f"门票/消费：{detail.get('ticket') or detail.get('cost') or '—'}"
    )
    if detail.get("culture"):
        summary += f"。{detail['culture'][:80]}"
    payload = {"type": "poi_detail", "poi": detail, "summary": summary}
    return text_response(json.dumps(payload, ensure_ascii=False))


@utility_mcp.tool(
    name="amap_transit_realtime",
    description="公交/地铁实时出行：查看到指定目的地的公共交通方案与预计耗时",
)
def amap_transit_realtime_tool(location: str, destination: str = "", city: str = ""):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    if not _is_coordinate(location):
        resolved = _resolve_location(location)
        if "error" in resolved:
            return text_response(resolved["error"])
        location = resolved["location"]

    city_name = city
    try:
        rg = requests.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"key": AMAP_API_KEY, "location": location, "output": "JSON"},
            timeout=8,
        )
        rd = rg.json()
        if rd.get("status") == "1":
            comp = rd.get("regeocode", {}).get("addressComponent", {})
            city_name = city_name or comp.get("city") or comp.get("province") or ""
    except Exception:
        pass

    lines: List[str] = []
    plans: List[dict] = []
    if destination:
        dest_info = _resolve_location(destination, city_name)
        if "error" in dest_info:
            return text_response(dest_info["error"])
        dest_loc = dest_info["location"]
        try:
            resp = requests.get(
                "https://restapi.amap.com/v5/direction/transit/integrated",
                params={
                    "key": AMAP_API_KEY,
                    "origin": location,
                    "destination": dest_loc,
                    "city1": city_name,
                    "city2": city_name,
                    "output": "JSON",
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") == "1":
                for path in ((data.get("route") or {}).get("transits") or [])[:3]:
                    duration = path.get("duration", "")
                    cost = path.get("cost", "")
                    segs = []
                    for seg in path.get("segments") or []:
                        bus = seg.get("bus") or {}
                        buslines = bus.get("buslines") or []
                        if buslines:
                            bl = buslines[0]
                            segs.append(
                                {
                                    "line": bl.get("name", ""),
                                    "departure": bl.get("departure_stop", {}).get("name", ""),
                                    "arrival": bl.get("arrival_stop", {}).get("name", ""),
                                    "via_num": bl.get("via_num", ""),
                                }
                            )
                    plan = {
                        "duration_sec": duration,
                        "duration_text": _format_duration(duration),
                        "cost": cost,
                        "segments": segs,
                    }
                    plans.append(plan)
                    lines.append(
                        f"方案：{' → '.join(s['line'] for s in segs if s.get('line')) or '步行换乘'}，"
                        f"约 {_format_duration(duration)}，费用约 {cost or '?'} 元"
                    )
        except Exception as e:
            lines.append(f"公交规划失败：{e}")

    nearby_stops: List[dict] = []
    try:
        resp = requests.get(
            "https://restapi.amap.com/v5/place/around",
            params={
                "key": AMAP_API_KEY,
                "location": location,
                "types": "150700|150500",
                "radius": 800,
                "page_size": 5,
                "output": "JSON",
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "1":
            for p in data.get("pois") or []:
                nearby_stops.append(
                    {
                        "name": p.get("name", ""),
                        "type": p.get("type", ""),
                        "distance": p.get("distance", ""),
                        "address": p.get("address", ""),
                    }
                )
            if nearby_stops:
                lines.append("附近站点：" + "、".join(s["name"] for s in nearby_stops[:3]))
    except Exception:
        pass

    summary = "\n".join(lines) if lines else "未找到公交实时方案，请尝试指定具体目的地"
    payload = {
        "type": "transit_realtime",
        "city": city_name,
        "origin": location,
        "destination": destination,
        "plans": plans,
        "nearby_stops": nearby_stops,
        "summary": summary,
    }
    return text_response(json.dumps(payload, ensure_ascii=False))


@utility_mcp.tool(
    name="plan_city_trip",
    description="生成城市旅游行程：结构化 JSON（日历+时间轴+POI间路线），适合多日行程规划。"
)
def plan_city_trip_tool(
    city: str,
    days: int = 3,
    focus: str = "mixed",
):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    days = max(1, min(days, 7))
    focus = focus if focus in ("mixed", "sightseeing", "food") else "mixed"

    from services.trip_builder import build_trip_plan

    weather_casts: List[dict] = []
    adcode_info = _resolve_location(city)
    if "adcode" in adcode_info and adcode_info.get("adcode"):
        try:
            weather_resp = requests.get(
                "https://restapi.amap.com/v3/weather/weatherInfo",
                params={
                    "key": AMAP_API_KEY,
                    "city": adcode_info["adcode"],
                    "extensions": "all",
                    "output": "JSON",
                },
                timeout=10,
            )
            wdata = weather_resp.json()
            if wdata.get("status") == "1" and wdata.get("forecasts"):
                weather_casts = wdata["forecasts"][0].get("casts", [])[:days]
        except Exception:
            pass

    def fetch_poi_struct(category: str) -> List[dict]:
        cfg = {
            "sightseeing": ("景点", "110000"),
            "food": ("美食", "050000"),
        }
        if category not in cfg:
            return []
        label, types = cfg[category]
        try:
            r = requests.get(
                "https://restapi.amap.com/v5/place/text",
                params={
                    "key": AMAP_API_KEY,
                    "keywords": label,
                    "types": types,
                    "city": city,
                    "page_size": 8,
                    "output": "JSON",
                },
                timeout=10,
            )
            data = r.json()
            if data.get("status") != "1":
                return []
            items = []
            for p in data.get("pois", [])[:8]:
                items.append(
                    {
                        "name": p.get("name", ""),
                        "address": p.get("address", ""),
                        "location": p.get("location", ""),
                        "type": p.get("type", label),
                    }
                )
            return items
        except Exception:
            return []

    sight_pois = fetch_poi_struct("sightseeing")
    food_pois = fetch_poi_struct("food")

    def route_fn(origin: str, dest: str, mode: str) -> Optional[dict]:
        try:
            r = requests.get(
                "https://restapi.amap.com/v3/direction/walking",
                params={
                    "key": AMAP_API_KEY,
                    "origin": origin,
                    "destination": dest,
                    "output": "JSON",
                },
                timeout=8,
            )
            data = r.json()
            if data.get("status") != "1":
                return None
            route = data.get("route", {})
            paths = route.get("paths") or []
            if not paths:
                return None
            p0 = paths[0]
            return {
                "distance": p0.get("distance"),
                "duration_text": _format_duration(p0.get("duration", 0)),
                "from_name": origin,
            }
        except Exception:
            return None

    trip = build_trip_plan(
        city=city,
        days=days,
        focus=focus,
        weather_casts=weather_casts,
        sight_pois=sight_pois,
        food_pois=food_pois,
        route_fn=route_fn,
        mode="walking",
    )
    from services.i18n import localize_poi_list

    for ev in trip.get("timeline", []):
        poi = ev.get("poi")
        if poi and poi.get("name"):
            ev["poi"]["display_name"] = localize_poi_list([poi], "zh")[0].get(
                "display_name", poi.get("name")
            )

    return text_response(json.dumps(trip, ensure_ascii=False))


MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "")


def _minimax_t2a(text: str, voice_id: str = "female-shaonv") -> dict:
    """调用 MiniMax 语音合成，返回 {path, url} 或 error"""
    if not MINIMAX_API_KEY:
        return {"error": "未配置 MINIMAX_API_KEY，请使用浏览器朗读"}
    url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={MINIMAX_GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "speech-02-hd",
        "text": text[:500],
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"format": "mp3", "sample_rate": 32000},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        data = resp.json()
        audio_hex = (data.get("data") or {}).get("audio", "")
        if not audio_hex:
            return {"error": data.get("base_resp", {}).get("status_msg", "TTS 失败")}
        out_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "data/audio"))
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"tts_{int(time.time())}.mp3"
        fpath = out_dir / fname
        fpath.write_bytes(bytes.fromhex(audio_hex))
        return {"path": str(fpath), "url": f"/static-audio/{fname}"}
    except Exception as e:
        return {"error": str(e)}


def _minimax_t2i(prompt: str, aspect_ratio: str = "16:9") -> dict:
    if not MINIMAX_API_KEY:
        return {"error": "未配置 MINIMAX_API_KEY"}
    url = f"https://api.minimax.chat/v1/image_generation?GroupId={MINIMAX_GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "image-01",
        "prompt": prompt[:800],
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        data = resp.json()
        images = (data.get("data") or {}).get("image_urls") or []
        if images:
            return {"url": images[0], "prompt": prompt}
        b64_list = (data.get("data") or {}).get("images") or []
        if b64_list:
            out_dir = Path(os.getenv("IMAGE_OUTPUT_DIR", "data/images"))
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = f"gen_{int(time.time())}.png"
            fpath = out_dir / fname
            import base64
            fpath.write_bytes(base64.b64decode(b64_list[0]))
            return {"url": f"/static-images/{fname}", "prompt": prompt}
        return {"error": data.get("base_resp", {}).get("status_msg", "图像生成失败")}
    except Exception as e:
        return {"error": str(e)}


@utility_mcp.tool(
    name="tts_speak",
    description="将文本转为语音文件（需 MiniMax API）。用户要求朗读、播报时使用。",
)
def tts_speak_tool(text: str, voice_id: str = "female-shaonv"):
    from services.speech_text import to_speech_text

    spoken = to_speech_text(text)
    if not spoken:
        return text_response("没有可朗读的有效文本。")
    result = _minimax_t2a(spoken, voice_id)
    if "error" in result:
        return text_response(f"TTS 不可用：{result['error']}。请提示用户使用浏览器朗读按钮。")
    return text_response(json.dumps({"type": "tts", **result}, ensure_ascii=False))


@utility_mcp.tool(
    name="analyze_scene_image",
    description="结合用户位置与场景描述（来自图片识景）搜索周边 POI 并给出解读",
)
def analyze_scene_image_tool(
    scene_description: str,
    location: str = "",
    keywords: str = "景点",
):
    parts = [f"【场景描述】\n{scene_description}"]
    if location and _is_coordinate(location):
        regeo_url = "https://restapi.amap.com/v3/geocode/regeo"
        try:
            r = requests.get(
                regeo_url,
                params={"key": AMAP_API_KEY, "location": location.strip(), "output": "JSON"},
                timeout=10,
            )
            rd = r.json()
            if rd.get("status") == "1":
                addr = rd.get("regeocode", {}).get("formatted_address", "")
                parts.insert(0, f"【当前位置】\n坐标：{location}\n地址：{addr}")
        except Exception:
            parts.insert(0, f"【当前位置】\n坐标：{location}")
        url = "https://restapi.amap.com/v5/place/around"
        params = {
            "key": AMAP_API_KEY,
            "location": location,
            "keywords": keywords,
            "radius": 2000,
            "page_size": 5,
            "output": "JSON",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("status") == "1" and data.get("pois"):
                lines = ["【周边相关 POI】"]
                for poi in data["pois"]:
                    lines.append(
                        f"- {poi.get('name')}（{poi.get('address', '')}，"
                        f"距离{poi.get('distance', '?')}米）"
                    )
                parts.append("\n".join(lines))
        except Exception as e:
            parts.append(f"周边搜索失败：{e}")
    return text_response("\n\n".join(parts))


@utility_mcp.tool(
    name="generate_poi_visual",
    description="根据 POI 名称或描述生成实景风格效果图（需 MiniMax API）",
)
def generate_poi_visual_tool(poi_name: str, style: str = "实景照片"):
    prompt = f"{poi_name}，{style}，中国城市，高清，自然光"
    result = _minimax_t2i(prompt)
    if "error" in result:
        return text_response(f"图像生成失败：{result['error']}")
    return text_response(json.dumps({"type": "image", **result}, ensure_ascii=False))


@utility_mcp.tool(
    name="amap_transit_nearby",
    description="查询坐标周边公交站/地铁站信息（实时公交站点）",
)
def amap_transit_nearby_tool(location: str, radius: int = 1000):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    if not _is_coordinate(location):
        resolved = _resolve_location(location)
        if "error" in resolved:
            return text_response(resolved["error"])
        location = resolved["location"]
    url = "https://restapi.amap.com/v5/place/around"
    params = {
        "key": AMAP_API_KEY,
        "location": location,
        "types": "150500|150700",
        "radius": min(radius, 3000),
        "page_size": 10,
        "output": "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response(f"未找到周边公交/地铁站点：{data.get('info', '')}")
        lines = ["周边公交/地铁站点："]
        poi_items = []
        for poi in data["pois"][:8]:
            name = poi.get("name", "")
            poi_type = poi.get("type", "")
            address = poi.get("address", "")
            distance = poi.get("distance", "")
            lines.append(
                f"- {name}（{poi_type}，距离{distance}米，{address}）"
            )
            loc_str = poi.get("location", "")
            if loc_str and "," in loc_str:
                try:
                    poi_items.append(
                        {
                            "name": name,
                            "address": address,
                            "type": poi_type,
                            "distance": distance,
                            "location": loc_str,
                            "lnglat": _parse_lnglat(loc_str),
                        }
                    )
                except (ValueError, TypeError):
                    pass
        summary = "\n".join(lines)
        if poi_items:
            try:
                center_lnglat = _parse_lnglat(location)
            except (ValueError, TypeError):
                center_lnglat = poi_items[0]["lnglat"]
            payload = {
                "summary": summary,
                "poi_map": {
                    "type": "poi_map",
                    "title": "附近地铁/公交站",
                    "show_path": False,
                    "center": {
                        "name": "当前位置",
                        "location": location,
                        "lnglat": center_lnglat,
                    },
                    "pois": poi_items,
                },
            }
            return text_response(json.dumps(payload, ensure_ascii=False))
        return text_response(summary)
    except Exception as e:
        return text_response(f"查询失败：{e}")


@utility_mcp.tool(
    name="amap_schema_navi",
    description="生成唤起高德 App 导航的 URI（含起点、终点与出行方式）",
)
def amap_schema_navi_tool(
    lon: str,
    lat: str,
    mode: str = "car",
    from_lon: str = "",
    from_lat: str = "",
    from_name: str = "起点",
    to_name: str = "终点",
):
    from services.amap_uri import build_amap_navi_uri

    origin = (
        {"lnglat": [float(from_lon), float(from_lat)], "name": from_name}
        if from_lon and from_lat
        else {}
    )
    destination = {"lnglat": [float(lon), float(lat)], "name": to_name}
    mode_key = {"car": "driving", "walk": "walking", "bus": "transit", "ride": "riding"}.get(mode, mode)
    uri = build_amap_navi_uri(origin, destination, mode_key)
    if not uri:
        return text_response("无法生成导航链接，请检查坐标")
    return text_response(
        json.dumps({"type": "deep_link", "label": "在高德 App 中导航", "uri": uri}, ensure_ascii=False)
    )


@utility_mcp.tool(
    name="amap_schema_taxi",
    description="生成唤起高德 App 叫车的 URI",
)
def amap_schema_taxi_tool(lon: str, lat: str, name: str = "目的地"):
    from urllib.parse import quote
    uri = f"https://uri.amap.com/taxi?dlat={lat}&dlon={lon}&dname={quote(name)}&dev=0"
    return text_response(json.dumps({"type": "deep_link", "label": "在高德 App 中叫车", "uri": uri}, ensure_ascii=False))


@utility_mcp.tool(
    name="emergency_nearest_hospital",
    description="查找最近医院并规划驾车路线，用于紧急医疗场景",
)
def emergency_nearest_hospital_tool(location: str):
    if not AMAP_API_KEY:
        return text_response("未配置高德地图API密钥")
    if not _is_coordinate(location):
        resolved = _resolve_location(location)
        if "error" in resolved:
            return text_response(resolved["error"])
        location = resolved["location"]
    url = "https://restapi.amap.com/v5/place/around"
    params = {
        "key": AMAP_API_KEY,
        "location": location,
        "keywords": "医院",
        "types": "090100",
        "radius": 5000,
        "page_size": 3,
        "output": "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1" or not data.get("pois"):
            return text_response("未找到附近医院，请立即拨打 120")
        hospital = data["pois"][0]
        h_name = hospital.get("name", "医院")
        h_loc = hospital.get("location", "")
        lines = [
            "【紧急医疗指引】",
            "如遇生命危险，请立即拨打 120！",
            f"最近医院：{h_name}（{hospital.get('address', '')}，距离{hospital.get('distance', '?')}米）",
        ]
        if h_loc:
            route_params = {
                "key": AMAP_API_KEY,
                "origin": location,
                "destination": h_loc,
                "show_fields": "polyline,cost",
                "output": "JSON",
            }
            try:
                rr = requests.get(
                    "https://restapi.amap.com/v5/direction/driving",
                    params=route_params,
                    timeout=15,
                )
                rd = rr.json()
                if rd.get("status") == "1":
                    paths = (rd.get("route") or {}).get("paths") or []
                    if paths:
                        p0 = paths[0]
                        lines.append(
                            f"驾车路线：约{p0.get('distance', '?')}米，"
                            f"预计{_format_duration(p0.get('duration', 0))}"
                        )
            except Exception:
                pass
            lng, lat = h_loc.split(",")
            uri = f"https://uri.amap.com/navigation?to={lng.strip()},{lat.strip()}&mode=car&coordinate=gaode"
            lines.append(f"高德导航：{uri}")
        return text_response("\n".join(lines))
    except Exception as e:
        return text_response(f"查询失败：{e}，请拨打 120")


# 运行 MCP 服务
if __name__ == "__main__":
    port = 7001 # 指定服务端口
    print(f"[MCP] 自定义 MCP 服务即将启动于 http://localhost:{port}")
    
    # create_fastapi_app 会将 FastMCP 实例转换为一个 FastAPI 应用
    app = create_fastapi_app(utility_mcp)
    
    # 使用 uvicorn 运行 FastAPI 应用
    # 这部分代码会阻塞，直到服务停止 (例如按 Ctrl+C)
    uvicorn.run(app, host="0.0.0.0", port=port)


