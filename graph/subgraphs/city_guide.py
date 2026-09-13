"""城市向导子 Agent"""
from graph.subgraphs.react_agent import build_react_subgraph

_compiled = None


def get_city_guide_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_react_subgraph("city_guide")
    return _compiled
