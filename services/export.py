"""行程导出与分享"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SHARE_DIR = Path("data/shares")


def trip_to_markdown(trip: Dict[str, Any]) -> str:
    title = trip.get("title") or f"{trip.get('city', '城市')} {trip.get('days', 1)} 日游"
    lines = [f"# {title}", ""]
    if trip.get("summary"):
        lines.append(trip["summary"])
        lines.append("")

    stops = trip.get("stops") or []
    if stops:
        lines.append("## 行程站点")
        for i, stop in enumerate(stops, 1):
            name = stop.get("name") or stop.get("title") or "站点"
            note = stop.get("note") or stop.get("time") or ""
            suffix = f" — {note}" if note else ""
            lines.append(f"{i}. **{name}**{suffix}")
        lines.append("")

    for day in trip.get("calendar", []):
        lines.append(f"## 第{day['day']}天 {day.get('date', '')} {day.get('weather', '')} {day.get('temp', '')}")
        day_events = [e for e in trip.get("timeline", []) if e.get("day") == day["day"]]
        for ev in day_events:
            poi = ev.get("poi", {})
            lines.append(f"- **{ev.get('time', '')}** {poi.get('name', '')} ({ev.get('category', '')})")
        lines.append("")
    routes = trip.get("routes", [])
    if routes:
        lines.append("## 路线串联")
        for r in routes:
            lines.append(
                f"- 第{r.get('day')}天 {r.get('from_name', '')} → {r.get('to_name', '')} "
                f"{r.get('duration_text', '')} ({r.get('mode', '')})"
            )
    return "\n".join(lines).strip()


def create_share_link(session_id: str, trip: Dict[str, Any], base_url: str = "") -> Dict[str, str]:
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    token = str(uuid.uuid4())[:8]
    payload = {
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "trip": trip,
        "markdown": trip_to_markdown(trip),
    }
    (SHARE_DIR / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    url = f"{base_url.rstrip('/')}/api/share/{token}" if base_url else f"/api/share/{token}"
    page_url = f"{base_url.rstrip('/')}/p/{token}" if base_url else f"/p/{token}"
    return {"token": token, "url": url, "page_url": page_url, "markdown": payload["markdown"]}


def load_share(token: str) -> Optional[Dict[str, Any]]:
    path = SHARE_DIR / f"{token}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def export_session_itinerary(messages: List[Dict[str, Any]]) -> str:
    lines = ["# 对话行程导出", ""]
    for m in messages:
        role = "用户" if m.get("role") == "user" else "助手"
        lines.append(f"**{role}**：{m.get('content', '')}")
        if m.get("route_map"):
            rm = m["route_map"]
            lines.append(f"  > 路线：{rm.get('origin', {}).get('name', '')} → {rm.get('destination', {}).get('name', '')}")
        lines.append("")
    return "\n".join(lines)
