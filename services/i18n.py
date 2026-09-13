"""多语言 POI 描述（中英）"""
from typing import Dict, Optional

_POI_EN: Dict[str, str] = {
    "故宫": "Forbidden City",
    "天安门": "Tiananmen Square",
    "长城": "Great Wall",
    "兵马俑": "Terracotta Army",
    "大雁塔": "Giant Wild Goose Pagoda",
    "钟楼": "Bell Tower",
    "回民街": "Muslim Quarter",
    "外滩": "The Bund",
    "东方明珠": "Oriental Pearl Tower",
}


def poi_bilingual(name: str, lang: str = "zh") -> str:
    if lang == "en" and name in _POI_EN:
        return f"{name} ({_POI_EN[name]})"
    if lang == "en":
        return name
    en = _POI_EN.get(name)
    return f"{name}（{en}）" if en else name


def localize_poi_list(pois: list, lang: str = "zh") -> list:
    result = []
    for poi in pois or []:
        item = dict(poi)
        name = item.get("name", "")
        item["display_name"] = poi_bilingual(name, lang)
        result.append(item)
    return result
