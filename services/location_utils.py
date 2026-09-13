"""从逆地理编码文本/组件中解析城市信息"""
import re
from typing import Any, Dict, Optional


def parse_city_from_regeo_text(text: str) -> Optional[str]:
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("城市："):
            city = line.split("：", 1)[-1].strip()
            if city and city not in ("[]", ""):
                return _normalize_city_name(city)
    for line in text.splitlines():
        if line.startswith("地址："):
            addr = line.split("：", 1)[-1].strip()
            cm = re.search(r"[\u4e00-\u9fa5]{2,10}?市", addr)
            if cm:
                return cm.group(0)
    return None


def _normalize_city_name(city: str) -> str:
    city = city.strip()
    if not city:
        return city
    if city.endswith("市") or city.endswith("省") or city.endswith("自治区"):
        return city
    if len(city) <= 8:
        return f"{city}市"
    return city


def format_location_label(city: str, district: str = "", address: str = "") -> str:
    if city and district:
        return f"{city} · {district}"
    if city:
        return city
    if address:
        return address[:24]
    return "当前位置"
