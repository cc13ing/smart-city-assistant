"""MCP 工具 HTTP 客户端（缓存 / 重试 / 熔断）"""
import os
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

from tools.cache import get_tool_cache

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:7001")
MCP_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "25"))
MCP_MAX_RETRIES = int(os.getenv("MCP_MAX_RETRIES", "2"))
MCP_CACHE_ENABLED = os.getenv("MCP_CACHE_ENABLED", "true").lower() == "true"

_CACHEABLE_TOOLS = frozenset(
    {
        "amap_place_around",
        "get_city_poi",
        "amap_regeocode",
        "amap_route_planning",
        "get_city_weather_cn",
        "amap_weather_forecast",
    }
)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> bool:
        if time.time() < self.open_until:
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.open_until = time.time() + self.reset_seconds


_breaker = CircuitBreaker()


def call_mcp_tool(
    tool_name: str,
    params: Dict[str, Any],
    mcp_url: str | None = None,
    *,
    use_cache: bool = True,
) -> str:
    base = (mcp_url or MCP_SERVER_URL).rstrip("/")
    if not base:
        return "错误：MCP 服务地址未配置"

    if use_cache and MCP_CACHE_ENABLED and tool_name in _CACHEABLE_TOOLS:
        cached = get_tool_cache().get(tool_name, params)
        if cached is not None:
            return cached

    if not _breaker.allow():
        return f"调用工具 {tool_name} 失败: MCP 服务熔断中，请稍后重试"

    last_err = ""
    for attempt in range(MCP_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{base}/tools/{tool_name}",
                json=params,
                timeout=MCP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            text = _extract_text(data)
            _breaker.record_success()
            if use_cache and MCP_CACHE_ENABLED and tool_name in _CACHEABLE_TOOLS:
                get_tool_cache().set(tool_name, params, text)
            return text
        except Exception as e:
            last_err = str(e)
            if attempt < MCP_MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))

    _breaker.record_failure()
    return f"调用工具 {tool_name} 失败: {last_err}"


def _extract_text(data: Dict[str, Any]) -> str:
    if data.get("content"):
        parts = data["content"]
        if isinstance(parts, list) and parts and "text" in parts[0]:
            return parts[0]["text"]
    return "工具执行成功，但未返回文本"


def reset_circuit_breaker() -> None:
    _breaker.failures = 0
    _breaker.open_until = 0.0
