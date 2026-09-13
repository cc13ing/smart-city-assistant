"""Kimi K2.6 多轮 tool call 消息兼容"""
from typing import List, Sequence

from langchain_core.messages import AIMessage, BaseMessage


def ensure_reasoning_on_tool_messages(messages: Sequence[BaseMessage]) -> List[BaseMessage]:
    """为含 tool_calls 的 assistant 消息补全 reasoning_content（Kimi 必填）"""
    fixed: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            kwargs = dict(msg.additional_kwargs or {})
            rc = kwargs.get("reasoning_content")
            if rc is None or rc == "":
                kwargs["reasoning_content"] = " "
            fixed.append(
                AIMessage(
                    content=msg.content or "",
                    tool_calls=msg.tool_calls,
                    additional_kwargs=kwargs,
                    id=msg.id,
                    response_metadata=getattr(msg, "response_metadata", None) or {},
                )
            )
        else:
            fixed.append(msg)
    return fixed
