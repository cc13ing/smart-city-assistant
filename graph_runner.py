"""LangGraph 运行器：对外提供城市助手 API（SSE 真流式）"""
import os
from typing import Any, Dict, Generator, List, Optional, Tuple

from langchain_core.messages import HumanMessage

import session_store
import user_profile
from graph.city_graph import get_city_graph
from graph.nodes import _stream_text_from_llm, finalize_node, resume_image_generation
from graph.state import CityAgentState
from llm_factory import OPENAI_MODEL, get_llm
from tools.mcp_client import MCP_SERVER_URL, call_mcp_tool


class CityGraphAgent:
    """LangGraph 驱动的城市助手"""

    def __init__(
        self,
        session_id: Optional[str] = None,
        mcp_url: str | None = None,
        device_id: Optional[str] = None,
    ):
        session = session_store.get_or_create_session(session_id)
        self.session_id = session["session_id"]
        self.mcp_url = (mcp_url or MCP_SERVER_URL).rstrip("/")
        if device_id and not session.get("device_id"):
            session["device_id"] = device_id
            session_store.save_session(session)
        self._device_id = session.get("device_id") or device_id or "default"
        self._session = session
        self._graph = get_city_graph()

    @property
    def user_location(self) -> str:
        return self._session.get("user_location", "")

    def set_user_location(self, location: str, label: str = "") -> None:
        if location:
            self._session["user_location"] = location
            self._session["user_location_label"] = label or location
            session_store.save_session(self._session)
            profile = user_profile.get_or_create_profile(self._device_id)
            user_profile.update_location(profile, location, label)
            user_profile.save_profile(profile)

    def get_proactive_suggestions(self) -> List[str]:
        profile = user_profile.get_or_create_profile(self._device_id)
        return user_profile.generate_proactive_suggestions(
            profile, has_location=bool(self.user_location)
        )

    def _call_mcp_tool(self, tool_name: str, params: dict) -> str:
        return call_mcp_tool(tool_name, params, self.mcp_url)

    def _graph_config(self) -> dict:
        return {"configurable": {"thread_id": self.session_id}}

    def _rollback_user_turn(self, user_text: str) -> None:
        session = session_store.get_session(self.session_id)
        if not session:
            return
        hist = session.get("conversation_history", [])
        if hist and hist[-1].get("role") == "user" and hist[-1].get("content") == user_text:
            hist.pop()
            session_store.save_session(session)

    def _base_input(self, user_text: str, **extra) -> CityAgentState:
        return {
            "session_id": self.session_id,
            "device_id": self._device_id,
            "user_text": user_text,
            "user_location": self._session.get("user_location", ""),
            "user_location_label": self._session.get("user_location_label", ""),
            "sse_events": [],
            **extra,
        }

    def _run_graph_stream(
        self, input_state: CityAgentState
    ) -> Tuple[Generator[Dict[str, Any], None, None], Dict[str, Any]]:
        config = self._graph_config()
        sse_emitted = 0
        holder: Dict[str, Any] = {}

        def event_gen() -> Generator[Dict[str, Any], None, None]:
            nonlocal sse_emitted
            for item in self._graph.stream(
                input_state,
                config,
                stream_mode=["updates", "custom"],
            ):
                if isinstance(item, tuple) and len(item) == 2:
                    mode, chunk = item
                else:
                    mode, chunk = "updates", item

                if mode == "custom" and isinstance(chunk, dict):
                    yield chunk
                    continue

                if mode != "updates" or not isinstance(chunk, dict):
                    continue

                for update in chunk.values():
                    if not isinstance(update, dict):
                        continue
                    events = update.get("sse_events") or []
                    while sse_emitted < len(events):
                        yield events[sse_emitted]
                        sse_emitted += 1

            snapshot = self._graph.get_state(config)
            holder.update(dict(snapshot.values) if snapshot else {})

        return event_gen(), holder

    def chat(self, user_text: str) -> str:
        result = ""
        for event in self.chat_stream(user_text):
            if event.get("type") == "done":
                result = event.get("content", "")
        return result

    def chat_stream(
        self,
        user_text: str,
        user_location: Optional[str] = None,
        location_label: str = "",
    ) -> Generator[Dict[str, Any], None, None]:
        if not user_text.strip():
            yield {"type": "error", "content": "消息不能为空"}
            return

        if user_location:
            self.set_user_location(user_location, location_label)

        events, state_holder = self._run_graph_stream(self._base_input(user_text))
        try:
            yield from events
            final_state = state_holder
        except Exception as e:
            self._rollback_user_turn(user_text)
            yield {"type": "error", "content": f"处理失败: {e}"}
            return

        if final_state.get("awaiting_image_confirm"):
            yield {
                "type": "confirm_required",
                "content": final_state.get("pending_image_prompt", ""),
                "session_id": self.session_id,
            }
            return

        if final_state.get("error"):
            self._rollback_user_turn(user_text)
            yield {"type": "error", "content": final_state["error"]}
            return

        final_response = final_state.get("final_response", "")
        if not final_response:
            yield {"type": "error", "content": "模型未返回有效内容，请重试。"}
            return

        done: Dict[str, Any] = {
            "type": "done",
            "content": final_response,
            "session_id": self.session_id,
        }
        if final_state.get("route_map"):
            done["route_map"] = final_state["route_map"]
        elif final_state.get("poi_map"):
            done["poi_map"] = final_state["poi_map"]
        elif final_state.get("traffic_map"):
            done["traffic_map"] = final_state["traffic_map"]
        if final_state.get("image_url"):
            done["image_url"] = final_state["image_url"]
        if final_state.get("trip_plan"):
            done["trip_plan"] = final_state["trip_plan"]
        yield done

    def resume_image_gen(self, confirm: bool = True) -> Generator[Dict[str, Any], None, None]:
        if not confirm:
            yield {"type": "done", "content": "已取消图像生成。", "session_id": self.session_id}
            return
        try:
            config = self._graph_config()
            snapshot = self._graph.get_state(config)
            merged = dict(snapshot.values) if snapshot else {}
            merged.update({"image_confirmed": True})
            result = resume_image_generation(merged)

            if result.get("image_url"):
                yield {"type": "image", "content": {"url": result["image_url"]}}

            final = result.get("final_response", "")
            if final:
                yield {"type": "token", "content": final}

            merged.update(result)
            finalize_node(merged)

            yield {
                "type": "done",
                "content": final,
                "session_id": self.session_id,
                "image_url": result.get("image_url"),
            }
        except Exception as e:
            yield {"type": "error", "content": str(e)}

    def analyze_image(
        self,
        image_base64: str,
        location: Optional[str] = None,
    ) -> str:
        loc = location or self.user_location
        vision_prompt = (
            "请用中文简要描述这张图片中的场景、建筑或店铺特征（2-4句），"
            "并推测可能是什么类型的地点。"
        )
        scene_desc = ""
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64[:800000]}"
                            },
                        },
                    ],
                }
            ]
            from openai import OpenAI

            client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1"),
            )
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=400,
            )
            scene_desc = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            scene_desc = f"用户上传了城市场景图片（视觉解析暂不可用：{e}）"

        raw = self._call_mcp_tool(
            "analyze_scene_image",
            {"scene_description": scene_desc, "location": loc or "", "keywords": "景点"},
        )
        llm = get_llm(streaming=True)
        prompt = (
            f"用户上传图片识景。\n场景：{scene_desc}\n\n工具结果：\n{raw}\n\n"
            "请结合 POI 数据给出通俗解读与推荐。"
        )
        return _stream_text_from_llm(llm, [HumanMessage(content=prompt)])


def get_city_agent(
    session_id: Optional[str] = None,
    device_id: Optional[str] = None,
    mcp_url: str | None = None,
) -> CityGraphAgent:
    session = session_store.get_or_create_session(session_id)
    did = device_id or session.get("device_id") or "default"
    return CityGraphAgent(session["session_id"], mcp_url=mcp_url, device_id=did)
