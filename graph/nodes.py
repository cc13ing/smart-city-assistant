"""LangGraph 节点实现"""
import json
from typing import Any, Dict, List, Literal

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.config import get_stream_writer

import session_store
import user_profile
from graph.intent_llm import (
    classify_user_intent,
    intent_analysis_to_state,
    nearby_poi_args_from_state,
)
from services.route_map_emit import should_emit_route_map
from graph.replan import (
    collect_exclude_stops_from_session,
    is_light_trip_request,
    is_replan_request,
    replan_context_block,
)
from graph.kimi_messages import ensure_reasoning_on_tool_messages
from graph.messages import history_to_messages, trim_conversation_messages
from graph.parsers import (
    normalize_route_args,
    parse_image_result,
    parse_poi_detail_result,
    parse_poi_map_result,
    parse_route_result,
    parse_traffic_result,
    parse_transit_realtime_result,
    parse_trip_plan_result,
)
from graph.state import CityAgentState
from llm_factory import get_llm


def _is_trip_prefetch_state(state: CityAgentState) -> bool:
    return bool(
        state.get("prefetch_halfday_trip")
        or state.get("prefetch_route")
        or state.get("needs_complex_planning")
        or state.get("intent") in ("complex", "route")
        or is_light_trip_request(state.get("user_text") or "")
    )
from tools.city_tools import get_tool_by_name, get_tools_for_agent
from tools.mcp_client import call_mcp_tool


def _emit_poi_map(
    poi_map: Dict[str, Any],
    device_id: str,
    location_context: str,
    tool_result_text: str,
    sse: List[Dict[str, Any]],
    status_msg: str,
) -> tuple:
    """个性化 poi_map、追加攻略上下文并写入 SSE。"""
    from services.poi_personalization import personalize_with_context

    personalized, guide_ctx = personalize_with_context(poi_map, device_id)
    if guide_ctx:
        location_context = (location_context + "\n\n" + guide_ctx).strip()
        tool_result_text += guide_ctx + "\n"
    sse.append({"type": "status", "content": status_msg})
    sse.append({"type": "poi_map", "content": personalized})
    return personalized, location_context, tool_result_text


def _personalize_poi_map_only(poi_map: Dict[str, Any], device_id: str) -> Dict[str, Any]:
    from services.poi_personalization import apply_poi_personalization

    return apply_poi_personalization(poi_map, device_id) or poi_map


def _route_city(state: CityAgentState) -> str:
    city = (state.get("query_city") or "").strip()
    if city:
        return city
    label = state.get("user_location_label") or ""
    if " · " in label:
        return label.split(" · ", 1)[0].strip()
    if label:
        return label
    profile = user_profile.get_or_create_profile(state.get("device_id") or "default")
    return profile.get("last_city") or ""


def _call_route_planning(
    state: CityAgentState,
    dest: str,
    mode: str,
    origin: str,
) -> str:
    """调用路线规划，优先使用会话/画像中的本地 POI 坐标。"""
    from services.route_destination import resolve_route_planning_args

    session = session_store.get_session(state.get("session_id", "")) or {}
    profile = user_profile.get_or_create_profile(state.get("device_id") or "default")
    args = resolve_route_planning_args(
        dest,
        origin=origin,
        mode=mode,
        city=_route_city(state),
        session_history=session.get("conversation_history"),
        profile=profile,
        trip_plan=state.get("trip_plan"),
        route_map=state.get("route_map"),
        poi_map=state.get("poi_map"),
    )
    mcp_args = {k: v for k, v in args.items() if not str(k).startswith("_")}
    return call_mcp_tool("amap_route_planning", mcp_args)

MAX_TOOL_LOOPS = 7

AGENT_PROMPTS = {
    "navigator": (
        "你是导航专家，只处理点到点路线与公共交通方案。"
        "优先使用 prefetch 已提供的 route_map；必要时调用 amap_route_planning、amap_transit_realtime。"
        "禁止查询附近美食/景点列表；禁止规划多日行程。"
        "用户已提供 GPS 时禁止再问在哪个城市。"
    ),
    "local_scout": (
        "你是本地探索专家，负责附近 POI、半日游/轻旅行与周边交通站点。"
        "优先依据 prefetch 的 poi_map、trip_plan 作答；可补充 amap_place_around。"
        "不要替用户规划跨城长途导航（交给导航专家）。"
    ),
    "city_guide": (
        "你是城市向导，负责城市推荐、POI 详情、天气预报。"
        "优先使用 prefetch 中的 POI/天气/详情文本；可调用 get_city_poi、get_poi_detail、get_city_weather_cn。"
        "不要规划具体驾车路线（交给导航专家）。"
    ),
    "creative": (
        "你是创意生成专家，负责效果图与场景图分析。"
        "仅可调用 generate_poi_visual（需用户确认）、analyze_scene_image、tts_speak。"
    ),
    "trip_planner": (
        "你是多日行程规划专家。优先 plan_city_trip、get_city_weather_cn、get_city_poi。"
        "给出按天划分的详细行程；不要处理单次「怎么走」导航。"
    ),
    "realtime_guard": (
        "你是实时守护专家。优先 amap_traffic_status、emergency_nearest_hospital。"
        "关注路况与安全；单次导航细节优先引用 prefetch。"
    ),
    "companion": (
        "你是温暖的城市伴游助手，处理闲聊与轻量问答。"
        "优先使用 prefetch 的 location_context；无数据时简洁回答，不要乱猜地点。"
    ),
    "general": (
        "你是城市向导（兼容模式）。"
        "用户已通过 GPS 提供坐标时禁止再问城市。"
    ),
}


def _append_sse(state: CityAgentState, event: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = list(state.get("sse_events") or [])
    events.append(event)
    return events


def load_context(state: CityAgentState) -> Dict[str, Any]:
    session_id = state.get("session_id") or ""
    device_id = state.get("device_id") or "default"
    session = session_store.get_or_create_session(session_id)
    if device_id and not session.get("device_id"):
        session["device_id"] = device_id
        session_store.save_session(session)

    profile = user_profile.get_or_create_profile(device_id)
    user_text = state.get("user_text", "")
    loc = state.get("user_location") or session.get("user_location", "")
    label = state.get("user_location_label") or session.get("user_location_label", "")

    if loc:
        session["user_location"] = loc
        session["user_location_label"] = label or loc
        user_profile.update_location(profile, loc, label)
        user_profile.save_profile(profile)

    if not session.get("title") or session.get("title") == "新对话":
        session["title"] = user_text[:30] + ("..." if len(user_text) > 30 else "")

    history = session.get("conversation_history", [])
    replan = is_replan_request(user_text)
    exclude_stops = collect_exclude_stops_from_session(session) if replan else []
    checkpoint_msgs = trim_conversation_messages(list(state.get("messages") or []))
    if not checkpoint_msgs and history:
        checkpoint_msgs = history_to_messages(history)

    lc_messages = checkpoint_msgs + [HumanMessage(content=user_text)]
    session.setdefault("conversation_history", []).append({"role": "user", "content": user_text})
    session_store.save_session(session)

    # 每轮重置 messages 为裁剪后的对话 + 本轮输入；单轮内 tool 消息由 checkpoint 正常累积
    reset_and_messages = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *lc_messages]

    return {
        "session_id": session["session_id"],
        "device_id": device_id,
        "user_location": loc,
        "user_location_label": label,
        "profile_summary": user_profile.profile_summary(profile),
        "messages": reset_and_messages,
        "tool_call_history": [],
        "tool_result_text": "",
        "location_context": "",
        "poi_map": None,
        "route_map": None,
        "traffic_map": None,
        "trip_plan": None,
        "image_url": None,
        "_tool_loop_count": 0,
        "awaiting_image_confirm": False,
        "image_confirmed": False,
        "pending_image_prompt": "",
        "intent": "",
        "active_agent": "",
        "query_city": "",
        "route_destination": "",
        "route_mode": "driving",
        "poi_name": "",
        "city_poi_category": "sightseeing",
        "nearby_keywords": "",
        "nearby_types": "",
        "nearby_radius": 2000,
        "subtasks": [],
        "prefetch_city_poi": False,
        "prefetch_weather": False,
        "prefetch_traffic": False,
        "prefetch_nearby": False,
        "prefetch_nearby_merged": False,
        "prefetch_halfday_trip": False,
        "prefetch_route": False,
        "prefetch_transit_station": False,
        "prefetch_poi_detail": False,
        "wants_navigation": False,
        "suppress_route_map": False,
        "needs_complex_planning": False,
        "replan_request": replan,
        "exclude_trip_stops": exclude_stops,
        "sse_events": _append_sse(state, {"type": "status", "content": "正在加载会话..."}),
    }


def classify_intent_node(state: CityAgentState) -> Dict[str, Any]:
    user_text = state.get("user_text", "")
    extra = ""
    if state.get("replan_request"):
        prev = ", ".join(state.get("exclude_trip_stops") or []) or "（见对话历史）"
        extra = f"\n【重要】用户要求重新规划，不满意上一轮方案。请避开或替换这些站点：{prev}"
    analysis = classify_user_intent(
        user_text + extra,
        has_location=bool(state.get("user_location")),
        location_label=state.get("user_location_label") or "",
    )
    updates: Dict[str, Any] = intent_analysis_to_state(analysis)
    if is_light_trip_request(user_text) and state.get("user_location"):
        updates["prefetch_halfday_trip"] = True
        updates["prefetch_traffic"] = False
        if updates.get("intent") in ("chat", "complex"):
            updates["intent"] = "nearby"
        updates["active_agent"] = "local_scout"
    if _is_trip_prefetch_state({**state, **updates}):
        updates["prefetch_traffic"] = False
    route_dest_hint = (updates.get("route_destination") or "").strip()
    if route_dest_hint and updates.get("intent") in ("route", "complex", "chat"):
        updates["prefetch_transit_station"] = False
        if updates.get("intent") == "chat" and (updates.get("prefetch_route") or updates.get("wants_navigation")):
            updates["intent"] = "route"
    subtasks = updates.get("subtasks") or []
    if subtasks:
        updates["sse_events"] = _append_sse(
            state,
            {
                "type": "status",
                "content": f"检测到复杂任务，正在规划 {len(subtasks)} 个子步骤...",
            },
        )
    return updates


def prefetch_node(state: CityAgentState) -> Dict[str, Any]:
    user_text = state.get("user_text", "")
    loc = state.get("user_location", "")
    query_city = (state.get("query_city") or "").strip()
    prefetch_city_poi = bool(state.get("prefetch_city_poi"))
    prefetch_weather = bool(state.get("prefetch_weather"))
    prefetch_traffic = bool(state.get("prefetch_traffic"))
    prefetch_nearby = bool(state.get("prefetch_nearby"))
    prefetch_nearby_merged = bool(state.get("prefetch_nearby_merged"))
    prefetch_halfday = bool(state.get("prefetch_halfday_trip")) or (
        is_light_trip_request(user_text) and bool(loc)
    )
    prefetch_route = bool(state.get("prefetch_route"))
    prefetch_transit = bool(state.get("prefetch_transit_station"))
    prefetch_poi_detail = bool(state.get("prefetch_poi_detail"))
    trip_prefetch = _is_trip_prefetch_state(state) or prefetch_halfday or prefetch_route
    prefetch_traffic = bool(state.get("prefetch_traffic")) and not trip_prefetch
    replan = bool(state.get("replan_request"))
    exclude_stops = list(state.get("exclude_trip_stops") or [])
    poi_name = (state.get("poi_name") or "").strip()
    route_dest = (state.get("route_destination") or "").strip()
    route_mode = (state.get("route_mode") or "driving").strip() or "driving"
    city_category = (state.get("city_poi_category") or "sightseeing").strip()
    location_context = state.get("location_context", "")
    tool_result_text = state.get("tool_result_text", "")
    poi_map = state.get("poi_map")
    route_map = state.get("route_map")
    traffic_map = state.get("traffic_map")
    trip_plan = state.get("trip_plan")
    sse = list(state.get("sse_events") or [])

    if replan:
        block = replan_context_block(user_text, exclude_stops)
        location_context = (location_context + "\n\n" + block).strip() if location_context else block
        tool_result_text += block + "\n"
        sse.append({"type": "status", "content": "正在根据您的反馈重新规划..."})

    if prefetch_poi_detail and poi_name:
        sse.append({"type": "status", "content": f"正在查询{poi_name}详情..."})
        detail_raw = call_mcp_tool(
            "get_poi_detail",
            {"keywords": poi_name, "city": query_city, "hint_location": loc or ""},
        )
        poi_detail = parse_poi_detail_result(detail_raw)
        if poi_detail and poi_detail.get("poi"):
            snippet = poi_detail.get("summary") or poi_detail["poi"].get("culture", "")
            block = f"【{poi_name}详情】\n{snippet}"
            location_context = (location_context + "\n\n" + block).strip() if location_context else block
            tool_result_text += block + "\n"

    if query_city and prefetch_city_poi and not prefetch_route:
        sse.append({"type": "status", "content": f"正在查询{query_city}热门景点..."})
        category = city_category if city_category in ("food", "sightseeing") else "sightseeing"
        raw = call_mcp_tool(
            "get_city_poi", {"city": query_city, "category": category, "page_size": 10}
        )
        parsed, summary = parse_poi_map_result(raw)
        block = f"【{query_city}-{'美食' if category == 'food' else '景点'}地图数据】\n{summary}"
        location_context = (location_context + "\n\n" + block).strip() if location_context else block
        tool_result_text += block + "\n"
        if parsed and parsed.get("pois"):
            poi_map = _personalize_poi_map_only(parsed, state.get("device_id", "default"))
            sse.append({"type": "status", "content": f"正在加载{query_city}景点地图..."})
            sse.append({"type": "poi_map", "content": poi_map})

    if prefetch_weather and query_city and not loc:
        sse.append({"type": "status", "content": f"正在查询{query_city}天气预报..."})
        weather_raw = call_mcp_tool("get_city_weather_cn", {"city": query_city})
        weather_block = f"【{query_city}天气预报与出行参考】\n{weather_raw}"
        location_context = (location_context + "\n\n" + weather_block).strip() if location_context else weather_block
        tool_result_text += weather_block + "\n"
        tool_result_text += (
            f"【出行建议要求】请基于{query_city}今日天气，给出穿衣、是否带伞、"
            f"适合户外/室内活动及交通方式建议。\n"
        )
    elif prefetch_weather and not loc and not query_city:
        tool_result_text += "【提示】用户询问天气但未定位，请提示其点击定位按钮后再查本地天气。\n"

    if loc:
        sse.append({"type": "status", "content": "正在根据您的位置查询..."})
        regeo = call_mcp_tool("amap_regeocode", {"location": loc})
        loc_block = f"【用户位置-逆地理编码】\n{regeo}"
        location_context = (location_context + "\n\n" + loc_block).strip() if location_context else loc_block
        tool_result_text += loc_block + "\n"

        from services.location_utils import parse_city_from_regeo_text

        city_from_gps = parse_city_from_regeo_text(regeo)
        if city_from_gps and (prefetch_weather or not query_city):
            query_city = query_city or city_from_gps

        if prefetch_weather:
            if not city_from_gps and not query_city:
                tool_result_text += "【提示】无法从 GPS 解析城市，请说明具体城市或重新定位。\n"
            else:
                target_city = query_city or city_from_gps
                sse.append({"type": "status", "content": f"正在查询{target_city}天气预报..."})
                weather_raw = call_mcp_tool("get_city_weather_cn", {"city": target_city})
                weather_block = f"【{target_city}天气预报与出行参考】\n{weather_raw}"
                location_context = (location_context + "\n\n" + weather_block).strip()
                tool_result_text += weather_block + "\n"
                tool_result_text += (
                    f"【出行建议要求】请基于{target_city}今日天气，给出穿衣、是否带伞、"
                    f"适合户外/室内活动及交通方式建议。\n"
                )

        if prefetch_halfday:
            from services.halfday_trip import build_halfday_trip_maps

            mode = route_mode

            def _route_fn(origin: str, dest: str, m: str):
                raw = _call_route_planning(
                    {**state, "query_city": query_city or _route_city(state)},
                    dest,
                    m,
                    origin,
                )
                return parse_route_result(raw)

            def _poi_fn():
                raw = call_mcp_tool(
                    "amap_place_around",
                    {
                        "location": loc,
                        "keywords": "景点",
                        "types": "110000",
                        "radius": 8000,
                        "page_size": 20 if replan else 10,
                    },
                )
                parsed, _ = parse_poi_map_result(raw)
                return parsed

            status = "正在根据反馈重新规划路线..." if replan else "正在规划半日游路线并在地图上标注..."
            sse.append({"type": "status", "content": status})
            trip_maps = build_halfday_trip_maps(
                loc,
                state.get("user_location_label") or "当前位置",
                _route_fn,
                _poi_fn,
                mode=mode,
                exclude_stop_names=exclude_stops if replan else None,
                skip_first=1 if replan else 0,
            )
            if trip_maps:
                poi_map = trip_maps["poi_map"]
                route_map = trip_maps["route_map"]
                ctx = trip_maps["context_text"]
                location_context = (location_context + "\n\n" + ctx).strip()
                tool_result_text += ctx + "\n"
                from services.trip_store import trip_from_halfday

                half_trip = trip_from_halfday(route_map, poi_map)
                trip_plan = half_trip
                sse.append({"type": "status", "content": "正在加载半日游地图..."})
                sse.append({"type": "poi_map", "content": poi_map})
                sse.append({"type": "route_map", "content": route_map})
                sse.append({"type": "trip_plan", "content": half_trip})

        elif prefetch_traffic:
            sse.append({"type": "status", "content": "正在查询周边实时路况..."})
            raw = call_mcp_tool("amap_traffic_status", {"location": loc, "radius": 1500})
            parsed, summary = parse_traffic_result(raw)
            block = f"【周边实时路况】\n{summary}"
            location_context = (location_context + "\n\n" + block).strip() if location_context else block
            tool_result_text += block + "\n"
            if parsed and parsed.get("center", {}).get("lnglat"):
                traffic_map = parsed
                poi_map = None
                route_map = None
                sse.append({"type": "status", "content": "正在加载路况地图..."})
                sse.append({"type": "traffic_map", "content": traffic_map})

        elif prefetch_nearby_merged and not prefetch_route and not query_city:
            from services.nearby_poi import fetch_merged_nearby
            from services.offline_cache import cache_poi, get_cached_poi

            parsed, summary = fetch_merged_nearby(
                loc,
                call_mcp_tool,
                parse_poi_map_result,
                get_cached_poi,
                cache_poi,
            )
            nearby_block = f"【用户位置-周边美食与景点】\n{summary}"
            location_context += "\n\n" + nearby_block
            tool_result_text += nearby_block + "\n"
            if parsed and parsed.get("pois") and not poi_map:
                poi_map, location_context, tool_result_text = _emit_poi_map(
                    parsed,
                    state.get("device_id", "default"),
                    location_context,
                    tool_result_text,
                    sse,
                    "正在加载周边美食与景点地图...",
                )

        elif prefetch_nearby and not prefetch_route and not query_city:
            from services.offline_cache import cache_poi, get_cached_poi

            args = {"location": loc, "page_size": 10, **nearby_poi_args_from_state(state)}
            cache_key = args.get("keywords", "")
            cached = get_cached_poi(loc, cache_key)
            parsed, summary = None, ""
            if cached and cached.get("parsed"):
                parsed = dict(cached["parsed"])
                parsed["offline"] = True
                summary = (cached.get("summary") or "") + "\n（离线缓存数据）"
            else:
                nearby_raw = call_mcp_tool("amap_place_around", args)
                parsed, summary = parse_poi_map_result(nearby_raw)
                if parsed:
                    cache_poi(loc, cache_key, {"parsed": parsed, "summary": summary})
                elif cached and cached.get("parsed"):
                    parsed = dict(cached["parsed"])
                    parsed["offline"] = True
                    summary = (cached.get("summary") or "") + "\n（离线缓存数据）"
            nearby_block = f"【用户位置-周边推荐】\n{summary}"
            location_context += "\n\n" + nearby_block
            tool_result_text += nearby_block + "\n"
            if parsed and parsed.get("pois") and not poi_map:
                poi_map, location_context, tool_result_text = _emit_poi_map(
                    parsed,
                    state.get("device_id", "default"),
                    location_context,
                    tool_result_text,
                    sse,
                    "正在加载周边景点地图...",
                )

    # 有明确终点时优先规划到该地名（避免被「附近地铁站」逻辑抢走路线）
    if loc and route_dest and (prefetch_route or state.get("wants_navigation") or state.get("intent") == "route"):
        mode = route_mode
        sse.append({"type": "status", "content": f"正在规划到{route_dest}的路线..."})
        raw = _call_route_planning(state, route_dest, mode, loc)
        route_data = parse_route_result(raw)
        if route_data and should_emit_route_map(state, route_data):
            route_map = route_data
            poi_map = None
            sse.append({"type": "route_map", "content": route_map})
            tool_result_text += f"【路线规划→{route_dest}】\n{route_data.get('summary', '')}\n"

    if loc and prefetch_transit and not route_dest:
        sse.append({"type": "status", "content": "正在查询附近地铁/公交站..."})
        raw = call_mcp_tool("amap_transit_nearby", {"location": loc, "radius": 1500})
        parsed, summary = parse_poi_map_result(raw)
        transit_block = f"【附近地铁/公交站】\n{summary}"
        location_context = (location_context + "\n\n" + transit_block).strip() if location_context else transit_block
        tool_result_text += transit_block + "\n"
        if parsed and parsed.get("pois"):
            poi_map = _personalize_poi_map_only(parsed, state.get("device_id", "default"))
            poi_map["title"] = parsed.get("title") or "附近地铁/公交站"
            poi_map["show_path"] = False
            sse.append({"type": "status", "content": "正在加载地铁/公交站地图..."})
            sse.append({"type": "poi_map", "content": poi_map})

            # 仅「怎么去附近地铁站」类问题：才用最近站点做步行路线
            if (prefetch_route or state.get("wants_navigation")) and not route_dest:
                subway_pois = [
                    p
                    for p in parsed["pois"]
                    if "地铁" in (p.get("name") or "") or "地铁" in (p.get("type") or "")
                ]
                candidates = subway_pois or parsed["pois"][:1]
                if candidates:
                    nearest = min(
                        candidates,
                        key=lambda p: int(p.get("distance") or 999999),
                    )
                    dest = nearest.get("location") or (
                        f"{nearest['lnglat'][0]},{nearest['lnglat'][1]}"
                        if nearest.get("lnglat")
                        else ""
                    )
                    if dest:
                        sse.append({"type": "status", "content": "正在规划步行路线..."})
                        route_raw = _call_route_planning(state, dest, "walking", loc)
                        route_data = parse_route_result(route_raw)
                        if route_data:
                            route_map = route_data
                            sse.append({"type": "route_map", "content": route_map})
                            tool_result_text += f"【步行路线】\n{route_data.get('summary', '')}\n"

    if loc and prefetch_route and not route_dest:
        dest = route_dest
        mode = route_mode
        if mode == "transit" and dest:
            sse.append({"type": "status", "content": "正在查询公交/地铁实时方案..."})
            tr_raw = call_mcp_tool(
                "amap_transit_realtime",
                {"location": loc, "destination": dest, "city": query_city or ""},
            )
            tr_data, tr_summary = parse_transit_realtime_result(tr_raw)
            if tr_data:
                tool_result_text += f"【公共交通】\n{tr_summary}\n"
                location_context = (location_context + "\n\n" + tr_summary).strip() if location_context else tr_summary
        sse.append({"type": "status", "content": "正在规划路线并在地图上标注..."})
        if dest:
            raw = _call_route_planning(state, dest, mode, loc)
            route_data = parse_route_result(raw)
            if route_data and should_emit_route_map(state, route_data):
                route_map = route_data
                poi_map = None
                sse.append({"type": "route_map", "content": route_map})
                tool_result_text += f"【路线规划】\n{route_data.get('summary', '')}\n"
    elif prefetch_route and not loc:
        tool_result_text += "【提示】用户询问路线但未提供 GPS 坐标，请提示其点击定位按钮。\n"

    sse.append({"type": "status", "content": "正在分析您的问题..."})
    updates: Dict[str, Any] = {
        "location_context": location_context,
        "tool_result_text": tool_result_text,
        "poi_map": poi_map,
        "route_map": route_map,
        "traffic_map": traffic_map,
        "trip_plan": trip_plan,
        "sse_events": sse,
    }
    if query_city:
        updates["query_city"] = query_city
    return updates


def _build_system_prompt(state: CityAgentState) -> str:
    from graph.agents import DEFAULT_SUBGRAPH, normalize_agent_name

    active = normalize_agent_name(state.get("active_agent") or DEFAULT_SUBGRAPH)
    base = AGENT_PROMPTS.get(active, AGENT_PROMPTS[DEFAULT_SUBGRAPH])
    parts = [base]
    profile = state.get("profile_summary", "")
    if profile:
        parts.append(profile)
        parts.append("请结合用户历史偏好给出个性化推荐。")
    loc_ctx = state.get("location_context", "")
    if loc_ctx:
        parts.append(loc_ctx)
    tool_text = state.get("tool_result_text", "")
    if tool_text:
        parts.append(f"已获取的数据：\n{tool_text}")
    subtasks = state.get("subtasks") or []
    if subtasks:
        parts.append("【复杂任务规划】请按以下子任务调用工具并整合：")
        for i, t in enumerate(subtasks, 1):
            parts.append(f"  {i}. {t}")
    loc = state.get("user_location", "")
    if loc:
        parts.append(f"用户坐标：{loc}（禁止再问在哪个城市）")
    if state.get("replan_request"):
        parts.append(replan_context_block(state.get("user_text", ""), state.get("exclude_trip_stops") or []))
    return "\n".join(parts)


def _stream_text_from_llm(llm, messages: List[Any]) -> str:
    """流式调用 LLM，通过 LangGraph custom stream 推送 token。"""
    writer = get_stream_writer()
    parts: List[str] = []
    response = None
    for chunk in llm.stream(messages):
        response = chunk if response is None else response + chunk
        if response and getattr(response, "tool_calls", None):
            continue
        content = chunk.content
        if not content:
            continue
        text = content if isinstance(content, str) else str(content)
        if text:
            writer({"type": "token", "content": text})
            parts.append(text)
    if parts:
        return "".join(parts)
    if response and response.content:
        return str(response.content).strip()
    return ""


def agent_node(state: CityAgentState) -> Dict[str, Any]:
    from graph.agents import DEFAULT_SUBGRAPH, normalize_agent_name

    active = normalize_agent_name(state.get("active_agent") or DEFAULT_SUBGRAPH)
    tools = get_tools_for_agent(active)
    llm = get_llm(streaming=True).bind_tools(tools)

    messages = ensure_reasoning_on_tool_messages(list(state.get("messages") or []))
    system = SystemMessage(content=_build_system_prompt(state))

    writer = get_stream_writer()
    response = None
    for chunk in llm.stream([system] + messages):
        response = chunk if response is None else response + chunk
        if response and getattr(response, "tool_calls", None):
            continue
        content = chunk.content
        if not content:
            continue
        text = content if isinstance(content, str) else str(content)
        if text:
            writer({"type": "token", "content": text})

    if response is None:
        response = AIMessage(content="")

    loop_count = state.get("_tool_loop_count", 0) + 1
    return {"messages": [response], "_tool_loop_count": loop_count}


def should_continue(state: CityAgentState) -> Literal["tools", "finalize"]:
    messages = state.get("messages") or []
    if not messages:
        return "finalize"
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        loop_count = state.get("_tool_loop_count", 0)
        if loop_count >= MAX_TOOL_LOOPS:
            return "finalize"
        return "tools"
    return "finalize"


def after_tools(state: CityAgentState) -> Literal["agent", "interrupt"]:
    if state.get("awaiting_image_confirm"):
        return "interrupt"
    return "agent"


def tools_node(state: CityAgentState) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    last = messages[-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {}

    user_text = state.get("user_text", "")
    loc = state.get("user_location", "")
    tool_result_text = state.get("tool_result_text", "")
    tool_history = list(state.get("tool_call_history") or [])
    poi_map = state.get("poi_map")
    route_map = state.get("route_map")
    traffic_map = state.get("traffic_map")
    trip_plan = state.get("trip_plan")
    image_url = state.get("image_url")
    sse = list(state.get("sse_events") or [])
    route_map_existing = state.get("route_map")
    nav_query = bool(state.get("wants_navigation")) or bool(state.get("prefetch_route"))
    traffic_query = bool(state.get("prefetch_traffic")) or state.get("intent") == "traffic"
    tool_messages: List[ToolMessage] = []

    for tc in last.tool_calls:
        name = tc["name"] if isinstance(tc, dict) else tc.name
        args = tc["args"] if isinstance(tc, dict) else tc.args
        tid = tc["id"] if isinstance(tc, dict) else tc.id

        if name == "generate_poi_visual" and not state.get("image_confirmed"):
            prompt = args.get("poi_name", "")
            return {
                "awaiting_image_confirm": True,
                "pending_image_prompt": prompt,
                "sse_events": sse + [{
                    "type": "image_confirm",
                    "content": {
                        "prompt": prompt,
                        "message": f"即将生成「{prompt}」效果图，是否继续？",
                    },
                }],
            }

        if name == "amap_route_planning":
            args = normalize_route_args(dict(args), loc)
            dest = str(args.get("destination", "")).strip()
            if dest and loc:
                enriched = _call_route_planning(state, dest, args.get("mode", "driving"), loc)
                route_data = parse_route_result(enriched)
                if route_data and should_emit_route_map(state, route_data):
                    summary = route_data.get("summary", "")
                    tool_result_text += f"工具 {name} 结果：{summary}\n"
                    tool_messages.append(ToolMessage(content=summary, tool_call_id=tid))
                    route_map = route_data
                    route_map_existing = route_map
                    sse.append({"type": "route_map", "content": route_map})
                    continue
            if route_map_existing:
                summary = route_map_existing.get("summary", "")
                tool_result_text += f"工具 {name}({args}) 结果：{summary}\n"
                tool_messages.append(ToolMessage(content=summary, tool_call_id=tid))
                continue

        sse.append({"type": "status", "content": f"正在调用工具：{name}..."})
        tool_fn = get_tool_by_name(name)
        if tool_fn:
            result = tool_fn.invoke(args)
        else:
            result = call_mcp_tool(name, args)

        route_data = parse_route_result(str(result))
        poi_data, poi_summary = parse_poi_map_result(str(result))
        traffic_data, traffic_summary = parse_traffic_result(str(result))
        trip_data = parse_trip_plan_result(str(result))
        transit_data, transit_summary = parse_transit_realtime_result(str(result))
        poi_detail = parse_poi_detail_result(str(result))
        img_data = parse_image_result(str(result))

        if trip_data:
            from services.trip_store import trip_from_plan

            trip_plan = trip_from_plan(trip_data)
            sse.append({"type": "trip_plan", "content": trip_plan})
            result_for_llm = trip_data.get("summary", str(result))
        elif poi_detail and poi_detail.get("poi"):
            poi = poi_detail["poi"]
            snippet = poi_detail.get("summary") or poi.get("culture", "")
            result_for_llm = snippet or str(result)
        elif transit_data and (transit_data.get("plans") or transit_data.get("nearby_stops")):
            result_for_llm = transit_summary
        elif img_data and img_data.get("url"):
            image_url = img_data["url"]
            sse.append({"type": "image", "content": {"url": image_url}})
            result_for_llm = f"已生成图片：{image_url}"
        elif traffic_data and traffic_data.get("center", {}).get("lnglat"):
            traffic_map = traffic_data
            poi_map = None
            sse.append({"type": "traffic_map", "content": traffic_map})
            result_for_llm = traffic_summary
        elif route_data and should_emit_route_map(state, route_data):
            route_map = route_data
            route_map_existing = route_map
            sse.append({"type": "route_map", "content": route_map})
            result_for_llm = route_data.get("summary", str(result))
        elif poi_data and poi_data.get("pois") and nav_query:
            result_for_llm = poi_summary
            if not route_map and loc:
                dest = (state.get("route_destination") or "").strip()
                if dest:
                    mode = (state.get("route_mode") or "driving").strip() or "driving"
                    route_raw = _call_route_planning(state, dest, mode, loc)
                    planned = parse_route_result(route_raw)
                    if planned and should_emit_route_map(state, planned):
                        route_map = planned
                        route_map_existing = route_map
                        sse.append({"type": "route_map", "content": route_map})
        elif poi_data and poi_data.get("pois") and not traffic_query and not traffic_map:
            poi_map = _personalize_poi_map_only(poi_data, state.get("device_id", "default"))
            sse.append({"type": "poi_map", "content": poi_map})
            result_for_llm = poi_summary
        elif route_data:
            result_for_llm = route_data.get("summary", str(result))
        else:
            result_for_llm = str(result)

        tool_history.append({"name": name, "args": args, "result": result_for_llm[:500]})
        tool_result_text += f"工具 {name}({args}) 结果：{result_for_llm}\n"
        tool_messages.append(ToolMessage(content=result_for_llm, tool_call_id=tid))

    if route_map or trip_plan:
        traffic_map = None

    return {
        "messages": tool_messages,
        "tool_result_text": tool_result_text,
        "tool_call_history": tool_history,
        "poi_map": poi_map,
        "route_map": route_map,
        "traffic_map": traffic_map,
        "trip_plan": trip_plan,
        "image_url": image_url,
        "sse_events": sse,
    }


def finalize_node(state: CityAgentState) -> Dict[str, Any]:
    messages = state.get("messages") or []
    final = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            final = str(msg.content).strip()
            break

    if not final and state.get("tool_result_text"):
        llm = get_llm(streaming=True)
        prompt = (
            f"用户问：{state.get('user_text', '')}\n"
            f"工具结果：\n{state.get('tool_result_text', '')}\n"
            "输出一句话，不要解释。请用不超过 50 字回答（用英文）"
        )
        final = _stream_text_from_llm(llm, [HumanMessage(content=prompt)])

    if not final:
        return {"error": "模型未返回有效内容", "final_response": ""}

    session_id = state.get("session_id", "")
    session = session_store.get_session(session_id)
    if session:
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": final}
        if state.get("route_map"):
            assistant_msg["route_map"] = state["route_map"]
        elif state.get("traffic_map"):
            assistant_msg["traffic_map"] = state["traffic_map"]
        elif state.get("poi_map"):
            assistant_msg["poi_map"] = state["poi_map"]
        if state.get("image_url"):
            assistant_msg["image_url"] = state["image_url"]
        if state.get("trip_plan"):
            assistant_msg["trip_plan"] = state["trip_plan"]
        session.setdefault("conversation_history", []).append(assistant_msg)
        session["tool_call_history"] = state.get("tool_call_history", [])
        session_store.save_session(session)

    device_id = state.get("device_id", "default")
    profile = user_profile.get_or_create_profile(device_id)
    user_text = state.get("user_text", "")
    user_profile.record_query_topic(profile, user_text)
    user_profile.update_preferences_from_text(profile, user_text)
    city = (state.get("query_city") or "").strip()
    if city:
        user_profile.record_poi(profile, city, city=city, category="city")
        profile["last_city"] = city
    poi_map = state.get("poi_map")
    if poi_map and poi_map.get("pois"):
        for poi in poi_map["pois"][:3]:
            user_profile.record_poi(
                profile,
                poi.get("name", ""),
                city=profile.get("last_city", ""),
                category=poi.get("type", ""),
                location=poi.get("location", ""),
            )
    route_map = state.get("route_map")
    if route_map:
        dest = route_map.get("destination", {})
        user_profile.record_route(
            profile,
            route_map.get("origin", {}).get("name", "起点"),
            dest.get("name", ""),
            route_map.get("mode", "driving"),
        )
    user_profile.save_profile(profile)

    return {"final_response": final}


def supervisor_dispatch(state: CityAgentState) -> Dict[str, Any]:
    """Supervisor：根据 active_agent 分发到对应子图，并推送路由状态。"""
    from graph.agents import SUBGRAPH_LABELS, normalize_agent_name
    from services.metrics import inc_agent_route

    active = normalize_agent_name(state.get("active_agent", "companion"))
    inc_agent_route(active)
    label = SUBGRAPH_LABELS.get(active, SUBGRAPH_LABELS["city_guide"])
    return {
        "sse_events": _append_sse(
            state,
            {"type": "status", "content": f"Supervisor 已路由至「{label}」子 Agent..."},
        )
    }


def route_to_subgraph(state: CityAgentState) -> str:
    from graph.agents import resolve_subgraph

    return resolve_subgraph(state.get("active_agent", "companion"))


def after_subgraph(state: CityAgentState) -> Literal["finalize", "interrupt"]:
    if state.get("awaiting_image_confirm"):
        return "interrupt"
    return "finalize"


def resume_image_generation(state: CityAgentState) -> Dict[str, Any]:
    """HITL：用户确认后执行图像生成"""
    prompt = state.get("pending_image_prompt", "")
    if not prompt:
        return {"error": "无待确认的图像生成任务"}
    raw = call_mcp_tool("generate_poi_visual", {"poi_name": prompt, "style": "实景照片"})
    img = parse_image_result(raw)
    sse = list(state.get("sse_events") or [])
    updates: Dict[str, Any] = {
        "awaiting_image_confirm": False,
        "image_confirmed": True,
        "pending_image_prompt": "",
    }
    if img and img.get("url"):
        updates["image_url"] = img["url"]
        sse.append({"type": "image", "content": {"url": img["url"]}})
        updates["final_response"] = f"已为您生成「{prompt}」效果图。"
    else:
        updates["final_response"] = raw
    updates["sse_events"] = sse
    return updates
