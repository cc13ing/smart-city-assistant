"""POI 文化攻略 + 详情 enrichment"""
from typing import Any, Dict, List, Optional

# 轻量 RAG：常见景点静态攻略（可后续换向量库）
POI_GUIDES: Dict[str, Dict[str, Any]] = {
    "钟楼": {
        "culture": "西安钟楼建于明洪武年间，是古代城市报时中心，与鼓楼遥相呼应。",
        "tips": "建议傍晚登楼，可俯瞰东大街夜景；周边回民街步行约 10 分钟。",
        "ticket_hint": "登楼需购票，以现场/官方渠道为准。",
        "best_time": "09:00-11:00 或 17:00-19:00",
    },
    "大雁塔": {
        "culture": "唐代玄奘译经之地，大雁塔北广场有亚洲最大音乐喷泉。",
        "tips": "北广场喷泉通常晚间举行；大慈恩寺需另购门票。",
        "ticket_hint": "大慈恩寺+登塔联票，价格随季节调整。",
        "best_time": "16:00-21:00",
    },
    "故宫": {
        "culture": "明清两代皇家宫殿，世界文化遗产。",
        "tips": "需提前预约，周一闭馆（法定节假日除外）。",
        "ticket_hint": "旺季建议提前 7 天预约。",
        "best_time": "08:30 开园入场",
    },
    "外滩": {
        "culture": "上海标志性滨水景观带，万国建筑博览群。",
        "tips": "夜景最佳；节假日人流大，注意错峰。",
        "ticket_hint": "外滩步行免费。",
        "best_time": "18:30-21:00",
    },
    "回民街": {
        "culture": "西安著名美食文化街区，汇聚牛羊肉泡馍、肉夹馍等地道小吃。",
        "tips": "建议错峰用餐；部分店铺只收现金，可备零钱。",
        "ticket_hint": "街区步行免费，餐饮另计。",
        "best_time": "11:30-13:30 或 18:00-20:30",
    },
    "兵马俑": {
        "culture": "秦始皇陵陪葬坑，被誉为世界第八大奇迹。",
        "tips": "建议预留半天；可与华清宫联游，注意防晒。",
        "ticket_hint": "需提前预约购票，价格以官方为准。",
        "best_time": "09:00 开园",
    },
    "华山": {
        "culture": "五岳之一，以险著称，适合挑战型徒步与观日出。",
        "tips": "夜爬看日出需备头灯与保暖衣物；恐高者慎选长空栈道。",
        "ticket_hint": "门票+索道联票，旺季排队较长。",
        "best_time": "05:00-07:00 观日出",
    },
    "大唐芙蓉园": {
        "culture": "盛唐主题皇家园林，夜景灯光与《梦回大唐》演出知名。",
        "tips": "夜场体验更佳；可与大唐不夜城串联游览。",
        "ticket_hint": "日场/夜场票价不同，以官方为准。",
        "best_time": "19:00-21:30",
    },
    "碑林": {
        "culture": "西安碑林博物馆，收藏历代碑石与书法珍品。",
        "tips": "与城墙南门邻近，可安排半日文化线。",
        "ticket_hint": "需购票入馆。",
        "best_time": "09:00-11:00",
    },
}


def enrich_poi_list_items(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """为推荐列表 POI 附加轻量攻略 chip 字段（不拉完整详情）。"""
    out: List[Dict[str, Any]] = []
    for poi in pois or []:
        p = dict(poi)
        guide = match_guide(p.get("name", ""))
        if guide:
            culture = guide.get("culture") or ""
            p["has_guide"] = True
            p["culture_hint"] = culture[:56] + ("…" if len(culture) > 56 else "")
        else:
            p["has_guide"] = False
        out.append(p)
    return out


def match_guide(poi_name: str) -> Optional[Dict[str, Any]]:
    if not poi_name:
        return None
    name = poi_name.strip()
    if name in POI_GUIDES:
        return POI_GUIDES[name]
    for key, guide in POI_GUIDES.items():
        if key in name or name in key:
            return guide
    return None


def enrich_poi_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    """合并 MCP 详情与静态攻略。"""
    name = detail.get("name") or ""
    guide = match_guide(name) or {}
    merged = dict(detail)
    if guide:
        merged["guide"] = guide
        merged["culture"] = guide.get("culture", "")
        merged["visit_tips"] = guide.get("tips", "")
        if not merged.get("ticket") and guide.get("ticket_hint"):
            merged["ticket"] = guide["ticket_hint"]
        if not merged.get("best_time") and guide.get("best_time"):
            merged["best_time"] = guide["best_time"]
    merged["has_guide"] = bool(guide)
    return merged


def guide_snippet_for_llm(poi_name: str) -> str:
    guide = match_guide(poi_name)
    if not guide:
        return ""
    parts = [f"【{poi_name}攻略】", guide.get("culture", "")]
    if guide.get("tips"):
        parts.append(f"游览建议：{guide['tips']}")
    if guide.get("ticket_hint"):
        parts.append(f"门票：{guide['ticket_hint']}")
    return "\n".join(p for p in parts if p)
