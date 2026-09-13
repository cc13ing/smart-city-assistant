"""可复用的 ReAct 子图工厂（agent ↔ tools 循环）"""
from typing import Literal

from langgraph.graph import END, START, StateGraph

from graph.agents import SUBGRAPH_LABELS
from graph.nodes import agent_node, tools_node
from graph.state import CityAgentState


def should_continue_react(state: CityAgentState) -> Literal["tools", "done"]:
    from graph.nodes import should_continue

    result = should_continue(state)
    return "tools" if result == "tools" else "done"


def after_tools_react(state: CityAgentState) -> Literal["agent", "interrupt"]:
    from graph.nodes import after_tools

    result = after_tools(state)
    return "interrupt" if result == "interrupt" else "agent"


def build_react_subgraph(agent_type: str):
    """构建独立 LangGraph 子图：START → agent ↔ tools → END。"""
    builder = StateGraph(CityAgentState)

    def _agent(state: CityAgentState):
        merged = {**state, "active_agent": agent_type}
        return agent_node(merged)

    builder.add_node("agent", _agent)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue_react,
        {"tools": "tools", "done": END},
    )
    builder.add_conditional_edges(
        "tools",
        after_tools_react,
        {"agent": "agent", "interrupt": END},
    )
    return builder.compile(name=f"{agent_type}_subgraph")


__all__ = ["SUBGRAPH_LABELS", "build_react_subgraph"]
