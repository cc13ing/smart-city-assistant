"""LangGraph 消息裁剪与 checkpoint 同步"""
from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def trim_conversation_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """跨轮次只保留用户消息与最终 assistant 文本，避免 tool 消息长期堆积。"""
    trimmed: List[BaseMessage] = []
    for msg in messages or []:
        if isinstance(msg, HumanMessage):
            content = str(msg.content or "").strip()
            if content:
                trimmed.append(HumanMessage(content=content, id=msg.id))
        elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            content = str(msg.content).strip()
            if content:
                trimmed.append(AIMessage(content=content, id=msg.id))
    return trimmed


def history_to_messages(history: List[dict]) -> List[BaseMessage]:
    """从 session UI 缓存引导 checkpoint（兼容旧数据）。"""
    messages: List[BaseMessage] = []
    for item in history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages
