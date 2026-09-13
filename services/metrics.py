"""简易运行指标（内存计数，供监控探针）"""
import time
from typing import Any, Dict

_started_at = time.time()
_counters: Dict[str, int] = {
    "chat_stream": 0,
    "companion_next": 0,
    "companion_track": 0,
    "trip_save": 0,
    "mcp_errors": 0,
}
_agent_route_counters: Dict[str, int] = {}


def inc(name: str, n: int = 1) -> None:
    _counters[name] = _counters.get(name, 0) + n


def inc_agent_route(agent: str) -> None:
    key = (agent or "unknown").strip()
    _agent_route_counters[key] = _agent_route_counters.get(key, 0) + 1


def snapshot() -> Dict[str, Any]:
    return {
        "uptime_seconds": int(time.time() - _started_at),
        "counters": dict(_counters),
        "agent_routes": dict(_agent_route_counters),
    }


def reset() -> None:
    for k in list(_counters.keys()):
        _counters[k] = 0
