"""用户画像持久化：跨会话偏好、历史 POI、常用路线"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILE_DIR = Path(os.getenv("PROFILE_DATA_DIR", "data/profiles"))
DEFAULT_DEVICE_ID = "default"

_MAX_POIS = 20
_MAX_ROUTES = 10
_MAX_CITIES = 10


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _profile_path(device_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in device_id)
    return PROFILE_DIR / f"{safe}.json"


def _empty_profile(device_id: str) -> Dict[str, Any]:
    return {
        "device_id": device_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "preferences": {
            "focus": "mixed",  # mixed | sightseeing | food
            "transport": "driving",  # driving | walking | transit | riding
            "time_of_day": "any",  # morning | afternoon | evening | any
        },
        "favorite_cities": [],
        "recent_pois": [],
        "recent_routes": [],
        "query_topics": [],  # e.g. ["天气", "美食", "路线"]
        "last_location": "",
        "last_location_label": "",
        "last_city": "",
        "poi_weights": {},
        "feedback_history": [],
    }


def ensure_profile_dir() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_profile(device_id: Optional[str] = None) -> Dict[str, Any]:
    ensure_profile_dir()
    did = (device_id or DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID
    path = _profile_path(did)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            profile.setdefault("device_id", did)
            profile.setdefault("preferences", _empty_profile(did)["preferences"])
            profile.setdefault("favorite_cities", [])
            profile.setdefault("recent_pois", [])
            profile.setdefault("recent_routes", [])
            profile.setdefault("query_topics", [])
            profile.setdefault("poi_weights", {})
            profile.setdefault("feedback_history", [])
            return profile
        except (json.JSONDecodeError, OSError):
            pass
    profile = _empty_profile(did)
    save_profile(profile)
    return profile


def save_profile(profile: Dict[str, Any]) -> None:
    ensure_profile_dir()
    profile["updated_at"] = _now_iso()
    did = profile.get("device_id", DEFAULT_DEVICE_ID)
    with open(_profile_path(did), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def delete_profile(device_id: str) -> bool:
    path = _profile_path(device_id)
    if path.exists():
        path.unlink()
        return True
    return False


def _dedupe_prepend(items: List[Any], new_item: Any, key_fn) -> List[Any]:
    seen = {key_fn(new_item)}
    result = [new_item]
    for item in items:
        k = key_fn(item)
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


def record_poi(
    profile: Dict[str, Any],
    name: str,
    city: str = "",
    category: str = "",
    location: str = "",
) -> None:
    if not name:
        return
    entry = {
        "name": name,
        "city": city,
        "category": category,
        "location": location,
        "visited_at": _now_iso(),
    }
    pois = profile.setdefault("recent_pois", [])
    profile["recent_pois"] = _dedupe_prepend(pois, entry, lambda x: x.get("name", ""))[:_MAX_POIS]
    if city and city not in profile.get("favorite_cities", []):
        cities = profile.setdefault("favorite_cities", [])
        cities.insert(0, city)
        profile["favorite_cities"] = list(dict.fromkeys(cities))[:_MAX_CITIES]


def record_city(profile: Dict[str, Any], city: str) -> None:
    """记录用户定位/查询城市，用于「我的城市」侧栏。"""
    if not city:
        return
    cities = profile.setdefault("favorite_cities", [])
    cities.insert(0, city)
    profile["favorite_cities"] = list(dict.fromkeys(cities))[:_MAX_CITIES]
    profile["last_city"] = city


def remove_favorite_city(profile: Dict[str, Any], city: str) -> None:
    """从常去城市列表移除指定城市。"""
    if not city:
        return
    profile["favorite_cities"] = [c for c in profile.get("favorite_cities", []) if c != city]
    if profile.get("last_city") == city:
        remaining = profile.get("favorite_cities") or []
        profile["last_city"] = remaining[0] if remaining else ""


def record_route(
    profile: Dict[str, Any],
    origin: str,
    destination: str,
    mode: str = "driving",
) -> None:
    if not destination:
        return
    entry = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "used_at": _now_iso(),
    }
    routes = profile.setdefault("recent_routes", [])
    profile["recent_routes"] = _dedupe_prepend(
        routes, entry, lambda x: f"{x.get('origin')}->{x.get('destination')}"
    )[:_MAX_ROUTES]


def record_query_topic(profile: Dict[str, Any], user_text: str) -> None:
    topics = profile.setdefault("query_topics", [])
    text = user_text.lower()
    topic_map = [
        ("美食", ["美食", "好吃", "餐厅", "吃", "小吃", "饭"]),
        ("景点", ["景点", "好玩", "游玩", "逛", "旅游"]),
        ("天气", ["天气", "下雨", "温度", "预报"]),
        ("路线", ["路线", "导航", "怎么走", "驾车", "公交", "步行"]),
        ("周边", ["附近", "周边", "周围"]),
    ]
    for label, keywords in topic_map:
        if any(k in user_text for k in keywords):
            if label not in topics:
                topics.insert(0, label)
    profile["query_topics"] = topics[:8]
    if any(k in user_text for k in ("美食", "好吃", "餐厅", "吃")):
        profile.setdefault("preferences", {})["focus"] = "food"
    elif any(k in user_text for k in ("景点", "好玩", "游玩", "逛")):
        profile.setdefault("preferences", {})["focus"] = "sightseeing"


def update_location(
    profile: Dict[str, Any],
    location: str,
    label: str = "",
    city: str = "",
) -> None:
    if location:
        profile["last_location"] = location
    if label:
        profile["last_location_label"] = label
    if city:
        profile["last_city"] = city


def update_preferences_from_text(profile: Dict[str, Any], user_text: str) -> None:
    prefs = profile.setdefault("preferences", {})
    if "步行" in user_text:
        prefs["transport"] = "walking"
    elif "公交" in user_text or "地铁" in user_text:
        prefs["transport"] = "transit"
    elif "骑行" in user_text or "骑车" in user_text:
        prefs["transport"] = "riding"
    elif any(k in user_text for k in ("驾车", "开车", "自驾")):
        prefs["transport"] = "driving"


def profile_summary(profile: Dict[str, Any]) -> str:
    prefs = profile.get("preferences", {})
    lines = ["【用户画像】"]
    focus = prefs.get("focus", "mixed")
    focus_label = {"food": "美食", "sightseeing": "景点", "mixed": "综合"}.get(focus, focus)
    lines.append(f"偏好类型：{focus_label}，常用出行：{prefs.get('transport', 'driving')}")
    cities = profile.get("favorite_cities", [])
    if cities:
        lines.append(f"关注城市：{', '.join(cities[:5])}")
    pois = profile.get("recent_pois", [])
    if pois:
        names = [p.get("name", "") for p in pois[:5] if p.get("name")]
        if names:
            lines.append(f"最近关注地点：{', '.join(names)}")
    routes = profile.get("recent_routes", [])
    if routes:
        r = routes[0]
        lines.append(f"最近路线：{r.get('origin', '?')} → {r.get('destination', '?')}")
    topics = profile.get("query_topics", [])
    if topics:
        lines.append(f"常问话题：{', '.join(topics[:5])}")
    from services.feedback import feedback_summary

    fb = feedback_summary(profile)
    if fb:
        lines.append(fb)
    if profile.get("last_city"):
        lines.append(f"上次所在城市：{profile['last_city']}")
    return "\n".join(lines)


def generate_proactive_suggestions(profile: Dict[str, Any], has_location: bool = False) -> List[str]:
    """根据画像生成 3-5 条主动建议 chips"""
    suggestions: List[str] = []
    prefs = profile.get("preferences", {})
    focus = prefs.get("focus", "mixed")
    cities = profile.get("favorite_cities", [])
    city = profile.get("last_city") or (cities[0] if cities else "")

    if has_location:
        if focus == "food":
            suggestions.append("附近有什么好吃的？")
            suggestions.append("推荐一家适合午餐的餐厅")
        elif focus == "sightseeing":
            suggestions.append("附近有什么好玩的景点？")
            suggestions.append("帮我规划今日3小时轻旅行")
        else:
            suggestions.append("附近有什么推荐？")
            suggestions.append("根据当前位置规划半日游")
        suggestions.append("从这里到最近地铁站怎么走？")
        suggestions.append("查询周边实时路况")
    elif city:
        if focus == "food":
            suggestions.append(f"{city}有什么必吃美食？")
        else:
            suggestions.append(f"推荐{city}的热门景点")
        suggestions.append(f"{city}今天天气怎么样？")
        suggestions.append(f"帮我规划{city}两日游行程")
    else:
        suggestions.append("深圳今天天气怎么样？")
        suggestions.append("推荐北京的热门景点")
        suggestions.append("帮我规划一个周末城市轻旅行")

    routes = profile.get("recent_routes", [])
    if routes and len(suggestions) < 5:
        dest = routes[0].get("destination", "")
        if dest:
            suggestions.append(f"从当前位置到{dest}怎么走？")

    pois = profile.get("recent_pois", [])
    if pois and len(suggestions) < 5:
        name = pois[0].get("name", "")
        if name:
            suggestions.append(f"介绍一下{name}")

    seen = set()
    unique: List[str] = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
        if len(unique) >= 5:
            break
    return unique


def new_device_id() -> str:
    return str(uuid.uuid4())
