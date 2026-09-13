"""LangGraph 状态定义"""
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CityAgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    session_id: str
    device_id: str
    user_text: str
    user_location: str
    user_location_label: str
    profile_summary: str
    intent: str
    active_agent: str
    query_city: str
    route_destination: str
    route_mode: str
    poi_name: str
    city_poi_category: str
    nearby_keywords: str
    nearby_types: str
    nearby_radius: int
    subtasks: List[str]
    prefetch_city_poi: bool
    prefetch_weather: bool
    prefetch_traffic: bool
    prefetch_nearby: bool
    prefetch_nearby_merged: bool
    prefetch_halfday_trip: bool
    prefetch_route: bool
    prefetch_transit_station: bool
    prefetch_poi_detail: bool
    wants_navigation: bool
    suppress_route_map: bool
    needs_complex_planning: bool
    replan_request: bool
    exclude_trip_stops: List[str]
    location_context: str
    tool_result_text: str
    tool_call_history: List[Dict[str, Any]]
    poi_map: Optional[Dict[str, Any]]
    route_map: Optional[Dict[str, Any]]
    traffic_map: Optional[Dict[str, Any]]
    image_url: Optional[str]
    trip_plan: Optional[Dict[str, Any]]
    final_response: str
    error: str
    pending_image_prompt: str
    awaiting_image_confirm: bool
    sse_events: List[Dict[str, Any]]
