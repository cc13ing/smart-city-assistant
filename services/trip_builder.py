"""结构化多日行程构建（日历 + 时间轴 + POI 间路线）"""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional


RouteFn = Callable[[str, str, str], Optional[Dict[str, Any]]]


def _slot_poi(pois: List[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
    if not pois:
        return None
    return pois[index % len(pois)]


def build_trip_plan(
    city: str,
    days: int,
    focus: str,
    weather_casts: List[Dict[str, Any]],
    sight_pois: List[Dict[str, Any]],
    food_pois: List[Dict[str, Any]],
    route_fn: Optional[RouteFn] = None,
    mode: str = "walking",
) -> Dict[str, Any]:
    """构建结构化行程 JSON（可独立单元测试）。"""
    days = max(1, min(days, 7))
    start = datetime.now().date()
    calendar: List[Dict[str, Any]] = []
    timeline: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []

    slots = [
        ("09:00", "morning", "sightseeing", sight_pois),
        ("12:00", "noon", "food", food_pois),
        ("14:30", "afternoon", "sightseeing", sight_pois),
        ("18:30", "evening", "food", food_pois),
    ]

    poi_idx = 0
    prev_loc: Optional[str] = None

    for d in range(days):
        day_date = (start + timedelta(days=d)).isoformat()
        cast = weather_casts[d] if d < len(weather_casts) else {}
        calendar.append(
            {
                "day": d + 1,
                "date": cast.get("date") or day_date,
                "weather": cast.get("dayweather", ""),
                "temp": f"{cast.get('nighttemp', '')}~{cast.get('daytemp', '')}℃",
            }
        )
        day_events: List[Dict[str, Any]] = []

        for time_str, period, category, pool in slots:
            if focus == "food" and category == "sightseeing":
                continue
            if focus == "sightseeing" and category == "food" and period == "noon":
                pass
            poi = _slot_poi(pool, poi_idx)
            if not poi:
                continue
            poi_idx += 1
            event = {
                "day": d + 1,
                "time": time_str,
                "period": period,
                "category": category,
                "poi": {
                    "name": poi.get("name", ""),
                    "location": poi.get("location", ""),
                    "address": poi.get("address", ""),
                },
            }
            day_events.append(event)

            loc = poi.get("location", "")
            if route_fn and prev_loc and loc:
                seg = route_fn(prev_loc, loc, mode)
                if seg:
                    routes.append(
                        {
                            "day": d + 1,
                            "from": prev_loc,
                            "to": loc,
                            "from_name": seg.get("from_name", ""),
                            "to_name": poi.get("name", ""),
                            "distance": seg.get("distance"),
                            "duration_text": seg.get("duration_text", ""),
                            "mode": mode,
                        }
                    )
            if loc:
                prev_loc = loc

        timeline.extend(day_events)

    summary_lines = [f"【{city}】{days}日结构化行程"]
    for c in calendar:
        summary_lines.append(f"  第{c['day']}天 {c['date']} {c['weather']} {c['temp']}")

    return {
        "type": "trip_plan",
        "city": city,
        "days": days,
        "focus": focus,
        "calendar": calendar,
        "timeline": timeline,
        "routes": routes,
        "summary": "\n".join(summary_lines),
    }
