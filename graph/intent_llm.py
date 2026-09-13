"""大模型意图识别：规则在 intent_prompt.md，代码只做解析与安全兜底。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from graph.agents import DEFAULT_SUBGRAPH, INTENT_DEFAULT_AGENT, normalize_agent_name
from graph.state import CityAgentState

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset(
    {
        "emergency",
        "route",
        "city_poi",
        "nearby",
        "complex",
        "image_gen",
        "poi_detail",
        "traffic",
        "weather",
        "chat",
    }
)
VALID_AGENTS = frozenset(
    {
        "navigator",
        "local_scout",
        "city_guide",
        "creative",
        "trip_planner",
        "realtime_guard",
        "companion",
        "general",
    }
)
VALID_ROUTE_MODES = frozenset({"driving", "walking", "riding", "transit"})
VALID_POI_CATEGORIES = frozenset({"food", "sightseeing"})

_EMERGENCY_KEYWORDS = ("紧急", "医院", "120", "急救")

_AGENT_FOR_INTENT = dict(INTENT_DEFAULT_AGENT)


@dataclass
class IntentAnalysis:
    intent: str = "chat"
    active_agent: str = DEFAULT_SUBGRAPH
    query_city: str = ""
    route_destination: str = ""
    route_mode: str = "driving"
    poi_name: str = ""
    city_poi_category: str = "sightseeing"
    nearby_keywords: str = ""
    nearby_types: str = ""
    nearby_radius: int = 2000
    subtasks: List[str] = field(default_factory=list)
    prefetch_city_poi: bool = False
    prefetch_weather: bool = False
    prefetch_traffic: bool = False
    prefetch_nearby: bool = False
    prefetch_nearby_merged: bool = False
    prefetch_halfday_trip: bool = False
    prefetch_route: bool = False
    prefetch_transit_station: bool = False
    prefetch_poi_detail: bool = False
    wants_navigation: bool = False
    suppress_route_map: bool = False
    needs_complex_planning: bool = False


@lru_cache(maxsize=1)
def get_intent_system_prompt() -> str:
    path = Path(__file__).with_name("intent_prompt.md")
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "你是意图分析器。只输出包含 intent 与 prefetch_* 等字段的 JSON。"


def _message_text(resp: Any) -> str:
    content = resp.content
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        joined = "".join(parts).strip()
        if joined:
            return joined
    ak = getattr(resp, "additional_kwargs", None) or {}
    if isinstance(ak.get("reasoning_content"), str) and ak["reasoning_content"].strip():
        return ak["reasoning_content"].strip()
    return str(content or "").strip()


def _parse_llm_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _coerce_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "是")
    if isinstance(val, (int, float)):
        return bool(val)
    return default


def _analysis_from_raw(raw: dict) -> IntentAnalysis:
    intent = str(raw.get("intent") or "chat").strip()
    if intent not in VALID_INTENTS:
        intent = "chat"

    agent = normalize_agent_name(str(raw.get("active_agent") or "companion"))

    route_mode = str(raw.get("route_mode") or "driving").strip().lower()
    if route_mode not in VALID_ROUTE_MODES:
        route_mode = "driving"

    category = str(raw.get("city_poi_category") or "sightseeing").strip().lower()
    if category not in VALID_POI_CATEGORIES:
        category = "sightseeing"

    try:
        radius = int(raw.get("nearby_radius") or 2000)
    except (TypeError, ValueError):
        radius = 2000
    radius = max(500, min(radius, 15000))

    subtasks = raw.get("subtasks") or []
    if not isinstance(subtasks, list):
        subtasks = []
    subtasks = [str(t).strip() for t in subtasks if str(t).strip()][:5]

    route_destination = str(raw.get("route_destination") or "").strip()
    poi_name = str(raw.get("poi_name") or "").strip()
    if route_destination and not poi_name:
        poi_name = route_destination

    return IntentAnalysis(
        intent=intent,
        active_agent=agent,
        query_city=str(raw.get("query_city") or "").strip().rstrip("市区县"),
        route_destination=route_destination,
        route_mode=route_mode,
        poi_name=poi_name,
        city_poi_category=category,
        nearby_keywords=str(raw.get("nearby_keywords") or "").strip(),
        nearby_types=str(raw.get("nearby_types") or "").strip(),
        nearby_radius=radius,
        subtasks=subtasks,
        prefetch_city_poi=_coerce_bool(raw.get("prefetch_city_poi")),
        prefetch_weather=_coerce_bool(raw.get("prefetch_weather")),
        prefetch_traffic=_coerce_bool(raw.get("prefetch_traffic")),
        prefetch_nearby=_coerce_bool(raw.get("prefetch_nearby")),
        prefetch_nearby_merged=_coerce_bool(raw.get("prefetch_nearby_merged")),
        prefetch_halfday_trip=_coerce_bool(raw.get("prefetch_halfday_trip")),
        prefetch_route=_coerce_bool(raw.get("prefetch_route")),
        prefetch_transit_station=_coerce_bool(raw.get("prefetch_transit_station")),
        prefetch_poi_detail=_coerce_bool(raw.get("prefetch_poi_detail")),
        wants_navigation=_coerce_bool(raw.get("wants_navigation")),
        suppress_route_map=_coerce_bool(raw.get("suppress_route_map")),
        needs_complex_planning=_coerce_bool(raw.get("needs_complex_planning")),
    )


def _apply_safety_rules(analysis: IntentAnalysis, user_text: str) -> IntentAnalysis:
    """仅保留安全与结构性兜底，业务语义交给 LLM + intent_prompt.md。"""
    if any(k in user_text for k in _EMERGENCY_KEYWORDS):
        analysis.intent = "emergency"
        analysis.active_agent = "realtime_guard"
        return analysis

    expected = _AGENT_FOR_INTENT.get(analysis.intent)
    if expected:
        analysis.active_agent = expected
    elif analysis.intent == "complex" or analysis.needs_complex_planning:
        analysis.active_agent = "trip_planner"
    elif analysis.intent == "chat":
        has_geo = any(
            [
                analysis.prefetch_route,
                analysis.prefetch_nearby,
                analysis.prefetch_city_poi,
                analysis.prefetch_poi_detail,
                analysis.query_city,
                analysis.prefetch_halfday_trip,
            ]
        )
        if not has_geo and analysis.active_agent == DEFAULT_SUBGRAPH:
            analysis.active_agent = "companion"

    analysis.active_agent = normalize_agent_name(analysis.active_agent)

    if analysis.needs_complex_planning and analysis.intent == "chat":
        analysis.intent = "complex"
        analysis.active_agent = "trip_planner"

    return analysis


def _apply_prefetch_invariants(analysis: IntentAnalysis) -> IntentAnalysis:
    """预取互斥：防止地图类型冲突（不替 LLM 猜意图）。"""
    dest = (analysis.route_destination or "").strip()

    if dest:
        analysis.prefetch_transit_station = False

    if analysis.prefetch_halfday_trip:
        analysis.prefetch_traffic = False
        analysis.prefetch_transit_station = False
        if not (dest and (analysis.prefetch_route or analysis.wants_navigation)):
            analysis.prefetch_route = False

    if (
        analysis.prefetch_halfday_trip
        or analysis.prefetch_route
        or analysis.needs_complex_planning
        or analysis.intent in ("complex", "route")
    ):
        analysis.prefetch_traffic = False

    return analysis


def _normalize_analysis(raw: dict, user_text: str) -> IntentAnalysis:
    analysis = _apply_prefetch_invariants(_apply_safety_rules(_analysis_from_raw(raw), user_text))
    return analysis


def _fallback_analysis(user_text: str, *, has_location: bool) -> IntentAnalysis:
    if any(k in user_text for k in _EMERGENCY_KEYWORDS):
        return IntentAnalysis(intent="emergency", active_agent="realtime_guard")
    return IntentAnalysis(
        intent="chat",
        active_agent=DEFAULT_SUBGRAPH if has_location else "companion",
    )


def classify_user_intent(
    user_text: str,
    *,
    has_location: bool = False,
    location_label: str = "",
) -> IntentAnalysis:
    text = (user_text or "").strip()
    if not text:
        return _fallback_analysis(text, has_location=has_location)

    if any(k in text for k in _EMERGENCY_KEYWORDS):
        return IntentAnalysis(intent="emergency", active_agent="realtime_guard")

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from llm_factory import OPENAI_API_KEY, get_intent_llm

        if not OPENAI_API_KEY:
            return _fallback_analysis(text, has_location=has_location)

        llm = get_intent_llm()
        loc_hint = "是" if has_location else "否"
        label_part = f"\n位置标签：{location_label}" if location_label else ""
        human = f"用户是否已提供 GPS 定位：{loc_hint}{label_part}\n用户输入：{text}"
        resp = llm.invoke(
            [SystemMessage(content=get_intent_system_prompt()), HumanMessage(content=human)]
        )
        data = _parse_llm_json(_message_text(resp))
        if not data:
            logger.warning("意图 JSON 解析失败，使用 fallback")
            return _fallback_analysis(text, has_location=has_location)
        return _normalize_analysis(data, text)
    except Exception:
        logger.exception("意图 LLM 调用失败，使用 fallback")
        return _fallback_analysis(text, has_location=has_location)


def intent_analysis_to_state(analysis: IntentAnalysis) -> Dict[str, Any]:
    return asdict(analysis)


def nearby_poi_args_from_state(state: CityAgentState) -> dict:
    keywords = (state.get("nearby_keywords") or "").strip()
    types = (state.get("nearby_types") or "").strip()
    try:
        radius = int(state.get("nearby_radius") or 2000)
    except (TypeError, ValueError):
        radius = 2000
    if not keywords and not types:
        return {"keywords": "", "types": "", "radius": radius}
    return {"keywords": keywords, "types": types, "radius": radius}


