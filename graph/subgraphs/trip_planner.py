"""行程规划子 Agent — 独立 LangGraph 子图"""
from graph.subgraphs.react_agent import build_react_subgraph

_compiled = None


def get_trip_planner_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_react_subgraph("trip_planner")
    return _compiled
