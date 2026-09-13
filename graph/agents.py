"""子 Agent 注册表：路由名、展示名、与 intent 的默认映射。"""
from __future__ import annotations

from typing import FrozenSet, Tuple

# LangGraph 子图节点名（与 build_react_subgraph(agent_type) 一致）
SUBGRAPH_NODE_NAMES: Tuple[str, ...] = (
    "navigator",
    "local_scout",
    "city_guide",
    "creative",
    "trip_planner",
    "realtime_guard",
    "companion",
)

SUBGRAPH_LABELS = {
    "navigator": "导航专家",
    "local_scout": "本地探索专家",
    "city_guide": "城市向导",
    "creative": "创意生成专家",
    "trip_planner": "行程规划专家",
    "realtime_guard": "实时守护专家",
    "companion": "城市伴游助手",
    # 兼容旧会话/checkpoint
    "general": "城市向导",
}

SUBGRAPH_NODE_NAMES_FROZEN: FrozenSet[str] = frozenset(SUBGRAPH_NODE_NAMES)

AGENT_ALIASES = {
    "general": "city_guide",
}

DEFAULT_SUBGRAPH = "city_guide"

INTENT_DEFAULT_AGENT = {
    "emergency": "realtime_guard",
    "traffic": "realtime_guard",
    "route": "navigator",
    "nearby": "local_scout",
    "city_poi": "city_guide",
    "poi_detail": "city_guide",
    "weather": "city_guide",
    "complex": "trip_planner",
    "image_gen": "creative",
    "chat": "companion",
}


def normalize_agent_name(active_agent: str) -> str:
    name = (active_agent or "").strip()
    if name in AGENT_ALIASES:
        return AGENT_ALIASES[name]
    if name in SUBGRAPH_NODE_NAMES_FROZEN:
        return name
    return DEFAULT_SUBGRAPH


def resolve_subgraph(active_agent: str) -> str:
    """Supervisor 路由：active_agent → 子图节点名。"""
    return normalize_agent_name(active_agent)
