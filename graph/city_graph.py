"""主状态图编译（Supervisor + 子 Agent 子图）"""
from langgraph.graph import END, START, StateGraph

from graph.agents import SUBGRAPH_NODE_NAMES
from graph.checkpoints import get_checkpointer
from graph.nodes import (
    after_subgraph,
    classify_intent_node,
    finalize_node,
    load_context,
    prefetch_node,
    resume_image_generation,
    route_to_subgraph,
    supervisor_dispatch,
)
from graph.state import CityAgentState
from graph.subgraphs import (
    get_city_guide_graph,
    get_companion_graph,
    get_creative_graph,
    get_local_scout_graph,
    get_navigator_graph,
    get_realtime_guard_graph,
    get_trip_planner_graph,
)

_SUBGRAPH_BUILDERS = {
    "navigator": get_navigator_graph,
    "local_scout": get_local_scout_graph,
    "city_guide": get_city_guide_graph,
    "creative": get_creative_graph,
    "trip_planner": get_trip_planner_graph,
    "realtime_guard": get_realtime_guard_graph,
    "companion": get_companion_graph,
}


def build_city_graph(*, with_checkpoint: bool = True):
    builder = StateGraph(CityAgentState)

    builder.add_node("load_context", load_context)
    builder.add_node("classify", classify_intent_node)
    builder.add_node("prefetch", prefetch_node)
    builder.add_node("supervisor", supervisor_dispatch)

    for name in SUBGRAPH_NODE_NAMES:
        builder.add_node(name, _SUBGRAPH_BUILDERS[name]())

    builder.add_node("finalize", finalize_node)
    builder.add_node("resume_image", resume_image_generation)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "classify")
    builder.add_edge("classify", "prefetch")
    builder.add_edge("prefetch", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_to_subgraph,
        {name: name for name in SUBGRAPH_NODE_NAMES},
    )

    for name in SUBGRAPH_NODE_NAMES:
        builder.add_conditional_edges(
            name,
            after_subgraph,
            {"finalize": "finalize", "interrupt": END},
        )

    builder.add_edge("finalize", END)
    builder.add_edge("resume_image", END)

    if with_checkpoint:
        return builder.compile(checkpointer=get_checkpointer())
    return builder.compile()


_compiled = None


def get_city_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_city_graph(with_checkpoint=True)
    return _compiled
