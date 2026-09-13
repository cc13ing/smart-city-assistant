"""解析 MCP 工具返回的结构化数据"""
import json
from typing import Any, Dict, Optional, Tuple


def parse_route_result(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("type") == "route":
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def parse_image_result(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("type") == "image":
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def parse_poi_map_result(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("poi_map"):
            return data["poi_map"], data.get("summary") or text
    except (json.JSONDecodeError, TypeError):
        pass
    return None, text


def parse_traffic_result(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("traffic_map"):
            return data["traffic_map"], data.get("summary") or text
    except (json.JSONDecodeError, TypeError):
        pass
    return None, text


def normalize_route_args(args: dict, user_location: str) -> dict:
    if not user_location:
        return args
    origin = str(args.get("origin", "")).strip()
    placeholders = ("我的位置", "当前位置", "我这里", "我所在", "我的坐标")
    if not origin or any(p in origin for p in placeholders):
        args = dict(args)
        args["origin"] = user_location
    return args


def parse_trip_plan_result(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("type") == "trip_plan":
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def parse_poi_detail_result(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("type") == "poi_detail":
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def parse_transit_realtime_result(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("type") == "transit_realtime":
            return data, data.get("summary") or text
    except (json.JSONDecodeError, TypeError):
        pass
    return None, text
