"""识别「重新规划」并提取上一轮行程站点，供预取/LLM 换方案。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

_REPLAN_HINTS = (
    "重新规划",
    "重新计划",
    "重新安排",
    "重新推荐",
    "不满意",
    "不喜欢",
    "换一个",
    "换个",
    "再来一次",
    "再来个",
    "不要这个",
    "换条",
    "重做",
    "改一改",
    "改一下",
    "再来一版",
    "别重复",
)


def is_replan_request(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return False
    return any(h in t for h in _REPLAN_HINTS)


def _norm_name(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"^第\d+站\s*", "", n)
    return n


def stop_names_from_trip_plan(trip: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    if not trip:
        return names
    for stop in trip.get("stops") or []:
        n = _norm_name(str(stop.get("name") or stop.get("display_name") or ""))
        if n:
            names.append(n)
    for ev in trip.get("timeline") or []:
        poi = ev.get("poi") or {}
        n = _norm_name(str(poi.get("name") or ""))
        if n:
            names.append(n)
    return names


def stop_names_from_route_map(route_map: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    if not route_map:
        return names
    dest = route_map.get("destination") or {}
    n = _norm_name(str(dest.get("name") or ""))
    if n and n not in ("当前位置",):
        names.append(n)
    for stop in route_map.get("stops") or []:
        n = _norm_name(str(stop.get("name") or ""))
        if n:
            names.append(n)
    return names


def collect_exclude_stops_from_session(session: Dict[str, Any]) -> List[str]:
    """从最近几轮助手回复中收集已推荐过的站点名。"""
    seen: Set[str] = set()
    ordered: List[str] = []
    history = session.get("conversation_history") or []
    for msg in reversed(history[-8:]):
        if msg.get("role") != "assistant":
            continue
        for trip in (msg.get("trip_plan"),):
            for n in stop_names_from_trip_plan(trip or {}):
                if n and n not in seen:
                    seen.add(n)
                    ordered.append(n)
        for n in stop_names_from_route_map(msg.get("route_map") or {}):
            if n and n not in seen:
                seen.add(n)
                ordered.append(n)
    return ordered


_LIGHT_TRIP_HINTS = ("轻旅行", "3小时", "三小时", "两小时", "2小时", "半日游", "一日游", "短途", "微旅行")
_TRIP_PLAN_HINTS = ("规划", "行程", "路线", "攻略", "去哪", "推荐", "玩", "旅游", "景点")


def is_light_trip_request(user_text: str) -> bool:
    """如「帮我规划今日3小时轻旅行」。"""
    t = (user_text or "").strip()
    if not t:
        return False
    if not any(k in t for k in _TRIP_PLAN_HINTS):
        return False
    return any(k in t for k in _LIGHT_TRIP_HINTS)


def replan_context_block(user_text: str, exclude_stops: List[str]) -> str:
    lines = [
        "【用户反馈】用户对上一轮行程/推荐不满意，明确要求重新规划。",
        f"用户原话：{user_text.strip()}",
        "你必须给出与上一轮明显不同的方案（更换景点/顺序/时段/交通方式），不要复述同一套站点与路线。",
    ]
    if exclude_stops:
        lines.append("上一轮已出现、请优先避开的站点：" + "、".join(exclude_stops[:12]))
    return "\n".join(lines)
