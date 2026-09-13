"""结构化行程存储与规范化"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

TRIP_DIR = Path(os.getenv("TRIP_DATA_DIR", "data/trips"))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _trip_path(trip_id: str) -> Path:
    return TRIP_DIR / f"{trip_id}.json"


def _safe_owner(owner_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (owner_id or "default"))


def normalize_trip(raw: Dict[str, Any], *, owner_id: str = "", trip_id: str = "") -> Dict[str, Any]:
    """统一 trip_plan / 半日游 / 手建行程 schema。"""
    tid = trip_id or raw.get("trip_id") or str(uuid.uuid4())
    timeline = list(raw.get("timeline") or [])
    stops: List[Dict[str, Any]] = list(raw.get("stops") or [])

    if not stops and timeline:
        for i, ev in enumerate(timeline):
            poi = ev.get("poi") or {}
            loc = poi.get("location") or ""
            lnglat = poi.get("lnglat")
            if not lnglat and loc and "," in loc:
                parts = loc.split(",")
                lnglat = [float(parts[0]), float(parts[1])]
            stops.append(
                {
                    "order": i + 1,
                    "name": poi.get("name") or ev.get("name") or f"第{i + 1}站",
                    "location": loc,
                    "lnglat": lnglat,
                    "time": ev.get("time", ""),
                    "period": ev.get("period", ""),
                    "category": ev.get("category", ""),
                    "visited": bool(ev.get("visited")),
                }
            )

    if not stops and raw.get("route_map"):
        rm = raw["route_map"]
        chain = [rm.get("origin")] + list(rm.get("stops") or []) + [rm.get("destination")]
        for i, p in enumerate(chain):
            if not p:
                continue
            stops.append(
                {
                    "order": len(stops) + 1,
                    "name": p.get("name", ""),
                    "location": p.get("location", ""),
                    "lnglat": p.get("lnglat"),
                    "visited": False,
                }
            )

    title = (
        raw.get("title")
        or raw.get("summary", "")[:40]
        or f"{raw.get('city', '城市')}行程"
    )
    return {
        "trip_id": tid,
        "type": raw.get("type") or "trip_plan",
        "owner_id": owner_id or raw.get("owner_id") or "default",
        "title": title,
        "city": raw.get("city", ""),
        "days": raw.get("days", 1),
        "focus": raw.get("focus", "mixed"),
        "calendar": list(raw.get("calendar") or []),
        "timeline": timeline,
        "routes": list(raw.get("routes") or []),
        "stops": stops,
        "route_map": raw.get("route_map"),
        "poi_map": raw.get("poi_map"),
        "favorite": bool(raw.get("favorite")),
        "active_stop_index": int(raw.get("active_stop_index") or 0),
        "status": raw.get("status") or "draft",
        "collaborators": list(raw.get("collaborators") or []),
        "share_token": raw.get("share_token") or "",
        "created_at": raw.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
    }


def trip_from_plan(plan: Dict[str, Any], owner_id: str = "") -> Dict[str, Any]:
    return normalize_trip({**plan, "type": "trip_plan"}, owner_id=owner_id)


def trip_from_halfday(route_map: Dict[str, Any], poi_map: Optional[Dict[str, Any]], owner_id: str = "") -> Dict[str, Any]:
    raw = {
        "type": "halfday",
        "title": route_map.get("summary") or "半日游",
        "city": "",
        "days": 1,
        "route_map": route_map,
        "poi_map": poi_map,
        "stops": [],
    }
    return normalize_trip(raw, owner_id=owner_id)


def save_trip(trip: Dict[str, Any]) -> Dict[str, Any]:
    TRIP_DIR.mkdir(parents=True, exist_ok=True)
    trip["updated_at"] = _now_iso()
    path = _trip_path(trip["trip_id"])
    path.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
    return trip


def get_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    path = _trip_path(trip_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_trip(trip_id: str) -> bool:
    path = _trip_path(trip_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_trips(owner_id: str, *, favorites_only: bool = False) -> List[Dict[str, Any]]:
    TRIP_DIR.mkdir(parents=True, exist_ok=True)
    trips: List[Dict[str, Any]] = []
    for path in TRIP_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("owner_id") != _safe_owner(owner_id):
            continue
        if favorites_only and not data.get("favorite"):
            continue
        trips.append(
            {
                "trip_id": data.get("trip_id", path.stem),
                "title": data.get("title", ""),
                "city": data.get("city", ""),
                "days": data.get("days", 1),
                "favorite": bool(data.get("favorite")),
                "status": data.get("status", "draft"),
                "stop_count": len(data.get("stops") or []),
                "updated_at": data.get("updated_at", ""),
            }
        )
    trips.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return trips


def update_trip(trip_id: str, owner_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    trip = get_trip(trip_id)
    if not trip or trip.get("owner_id") != _safe_owner(owner_id):
        return None
    allowed = {
        "title",
        "stops",
        "timeline",
        "calendar",
        "routes",
        "favorite",
        "active_stop_index",
        "status",
        "collaborators",
    }
    for key, val in patch.items():
        if key in allowed:
            trip[key] = val
    if patch.get("stops"):
        trip = normalize_trip(trip, owner_id=trip.get("owner_id", ""), trip_id=trip_id)
    return save_trip(trip)


def add_collaborator(trip_id: str, owner_id: str, collaborator_id: str) -> Optional[Dict[str, Any]]:
    trip = get_trip(trip_id)
    if not trip or trip.get("owner_id") != _safe_owner(owner_id):
        return None
    collabs = trip.setdefault("collaborators", [])
    cid = _safe_owner(collaborator_id)
    if cid not in collabs and cid != trip.get("owner_id"):
        collabs.append(cid)
    return save_trip(trip)


def mark_stop_visited(trip_id: str, stop_index: int) -> Optional[Dict[str, Any]]:
    trip = get_trip(trip_id)
    if not trip:
        return None
    stops = trip.get("stops") or []
    if 0 <= stop_index < len(stops):
        stops[stop_index]["visited"] = True
        trip["active_stop_index"] = min(stop_index + 1, len(stops) - 1)
        trip["stops"] = stops
        if stop_index >= len(stops) - 1:
            trip["status"] = "completed"
        else:
            trip["status"] = "in_progress"
        return save_trip(trip)
    return trip
