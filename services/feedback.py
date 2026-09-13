"""用户反馈：thumbs up/down 写入画像权重（单次投票，可切换/取消）"""
from typing import Any, Dict, List, Optional

VALID_CATEGORIES = frozenset({"poi", "route", "trip", "reply", "traffic"})


def feedback_key(category: str, target: str) -> str:
    cat = category if category in VALID_CATEGORIES else "poi"
    return f"{cat}:{target.strip()}"


def normalize_target(target: str, max_len: int = 200) -> str:
    return " ".join((target or "").split())[:max_len]


def record_feedback(
    profile: Dict[str, Any],
    target: str,
    rating: int,
    category: str = "poi",
) -> Dict[str, Any]:
    """
    对单一目标记录反馈。
    - 首次点击：设为 +1 / -1
    - 再次点击相同方向：取消（权重归零）
    - 点击相反方向：切换为新的 ±1（不累加）
    """
    target = normalize_target(target)
    if not target:
        return {"ok": False, "error": "empty_target"}
    if rating not in (1, -1):
        return {"ok": False, "error": "invalid_rating"}

    key = feedback_key(category, target)
    weights = profile.setdefault("poi_weights", {})
    current = weights.get(key, 0)

    if current == rating:
        weights.pop(key, None)
        new_weight = 0
        action = "removed"
    else:
        weights[key] = rating
        new_weight = rating
        action = "set"

    profile["poi_weights"] = weights
    history = profile.setdefault("feedback_history", [])
    history.insert(
        0,
        {
            "target": target,
            "category": category if category in VALID_CATEGORIES else "poi",
            "rating": rating,
            "action": action,
            "weight": new_weight,
        },
    )
    profile["feedback_history"] = history[:50]

    return {
        "ok": True,
        "key": key,
        "category": category,
        "target": target,
        "weight": new_weight,
        "action": action,
    }


def record_feedback_batch(
    profile: Dict[str, Any],
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """批量记录；相同 key 仅应用最后一次。"""
    merged: Dict[str, Dict[str, Any]] = {}
    for item in items or []:
        t = normalize_target(str(item.get("target", "")))
        if not t:
            continue
        cat = item.get("category", "poi")
        rating = item.get("rating")
        if rating not in (1, -1):
            continue
        key = feedback_key(cat, t)
        merged[key] = {"target": t, "category": cat, "rating": rating}

    results = []
    for item in merged.values():
        results.append(
            record_feedback(profile, item["target"], item["rating"], item["category"])
        )
    return results


def apply_weights_to_pois(pois: list, profile: Dict[str, Any]) -> list:
    weights = profile.get("poi_weights", {})
    scored = []
    for poi in pois or []:
        name = poi.get("name", "")
        w = weights.get(f"poi:{name}", 0)
        scored.append((w, poi))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def annotate_and_sort_pois(pois: list, profile: Dict[str, Any]) -> list:
    """为每个 POI 标注 preference_weight 并按权重降序排列。"""
    weights = profile.get("poi_weights", {})
    annotated = []
    for poi in pois or []:
        p = dict(poi)
        name = p.get("name", "")
        p["preference_weight"] = weights.get(f"poi:{name}", 0)
        annotated.append(p)
    annotated.sort(key=lambda p: p.get("preference_weight", 0), reverse=True)
    return annotated


def clear_all_feedback(profile: Dict[str, Any]) -> None:
    profile["poi_weights"] = {}
    profile["feedback_history"] = []


def remove_feedback_entry(
    profile: Dict[str, Any],
    target: str,
    category: str = "poi",
) -> bool:
    """删除单条反馈权重及历史中对应记录。"""
    target = normalize_target(target)
    if not target:
        return False
    cat = category if category in VALID_CATEGORIES else "poi"
    key = feedback_key(cat, target)
    weights = profile.setdefault("poi_weights", {})
    removed = key in weights
    weights.pop(key, None)
    profile["poi_weights"] = weights
    history = profile.get("feedback_history", [])
    profile["feedback_history"] = [
        h
        for h in history
        if not (h.get("target") == target and h.get("category") == cat)
    ]
    return removed


def route_weight(profile: Dict[str, Any], destination: str) -> int:
    return profile.get("poi_weights", {}).get(f"route:{destination.strip()}", 0)


def feedback_summary(profile: Dict[str, Any]) -> str:
    weights = profile.get("poi_weights", {})
    parts: List[str] = []

    def names(prefix: str, positive: bool) -> List[str]:
        out = []
        for key, val in weights.items():
            if not key.startswith(f"{prefix}:"):
                continue
            if positive and val > 0:
                out.append(key.split(":", 1)[1])
            elif not positive and val < 0:
                out.append(key.split(":", 1)[1])
        return out

    poi_likes = names("poi", True)
    poi_dislikes = names("poi", False)
    route_likes = names("route", True)
    route_dislikes = names("route", False)

    if poi_likes:
        parts.append(f"喜欢的地点：{', '.join(poi_likes[:5])}")
    if poi_dislikes:
        parts.append(f"不喜欢的地点：{', '.join(poi_dislikes[:5])}")
    if route_likes:
        parts.append(f"喜欢的路线终点：{', '.join(route_likes[:3])}")
    if route_dislikes:
        parts.append(f"不喜欢的路线终点：{', '.join(route_dislikes[:3])}")

    return "；".join(parts) if parts else ""
