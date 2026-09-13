"""是否向前端推送路线地图（结合意图 suppress 标志与路线距离）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from graph.state import CityAgentState

_NEARBY_MAX_ROUTE_METERS = 120_000


def should_emit_route_map(state: CityAgentState, route_data: Optional[dict]) -> bool:
    if state.get("suppress_route_map"):
        return False
    if not route_data or route_data.get("path_fallback"):
        return False
    try:
        dist = int(route_data.get("distance", 0))
    except (TypeError, ValueError):
        dist = 0
    if state.get("intent") == "nearby" and dist > _NEARBY_MAX_ROUTE_METERS:
        return False
    if dist > 500_000 and not (state.get("route_destination") or "").strip():
        return False
    return True
