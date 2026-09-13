"""实时守护子 Agent — 独立 LangGraph 子图"""
from graph.subgraphs.react_agent import build_react_subgraph

_compiled = None


def get_realtime_guard_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_react_subgraph("realtime_guard")
    return _compiled
