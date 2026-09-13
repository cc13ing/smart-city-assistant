"""导航专家子 Agent"""
from graph.subgraphs.react_agent import build_react_subgraph

_compiled = None


def get_navigator_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_react_subgraph("navigator")
    return _compiled
