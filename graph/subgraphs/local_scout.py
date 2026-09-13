"""本地探索专家子 Agent"""
from graph.subgraphs.react_agent import build_react_subgraph

_compiled = None


def get_local_scout_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_react_subgraph("local_scout")
    return _compiled
