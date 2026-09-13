"""POI 列表个性化：权重排序 + 轻量攻略摘要"""
from typing import Any, Dict, List, Optional, Tuple

from services.feedback import annotate_and_sort_pois
from services.poi_guide import enrich_poi_list_items, guide_snippet_for_llm


def apply_poi_personalization(
    poi_map: Optional[Dict[str, Any]],
    device_id: str,
) -> Optional[Dict[str, Any]]:
    """对 poi_map 应用用户权重排序并注入攻略 chip 字段。"""
    if not poi_map or not poi_map.get("pois"):
        return poi_map

    import user_profile

    profile = user_profile.get_or_create_profile(device_id or "default")
    pois = enrich_poi_list_items(list(poi_map.get("pois") or []))
    out = dict(poi_map)
    out["pois"] = annotate_and_sort_pois(pois, profile)
    return out


def guide_context_for_poi_map(poi_map: Optional[Dict[str, Any]], limit: int = 3) -> str:
    """为 LLM / location_context 生成命中静态攻略的摘要块。"""
    if not poi_map or not poi_map.get("pois"):
        return ""
    snippets: List[str] = []
    for poi in poi_map["pois"]:
        if not poi.get("has_guide"):
            continue
        text = guide_snippet_for_llm(poi.get("name", ""))
        if text:
            snippets.append(text)
        if len(snippets) >= limit:
            break
    if not snippets:
        return ""
    return "【个性化推荐-攻略摘要】\n" + "\n\n".join(snippets)


def personalize_with_context(
    poi_map: Optional[Dict[str, Any]],
    device_id: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """返回个性化后的 poi_map 及可追加到 location_context 的攻略文本。"""
    personalized = apply_poi_personalization(poi_map, device_id)
    ctx = guide_context_for_poi_map(personalized)
    return personalized, ctx
