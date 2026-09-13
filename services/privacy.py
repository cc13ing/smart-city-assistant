"""隐私与安全：位置脱敏、未成年人模式"""
import os
import re
from typing import Optional


def mask_location(location: str, precision: int = 2) -> str:
    """将经纬度脱敏到指定小数位（默认约 1km 精度）。"""
    if not location or "," not in location:
        return location
    parts = location.split(",", 1)
    try:
        lng = round(float(parts[0].strip()), precision)
        lat = round(float(parts[1].strip()), precision)
        return f"{lng},{lat}"
    except ValueError:
        return location


def is_minor_mode(device_id: Optional[str] = None) -> bool:
    if os.getenv("MINOR_MODE", "false").lower() == "true":
        return True
    return False


def sanitize_for_minor(text: str) -> str:
    """未成年人模式下过滤敏感词（简单规则）。"""
    if not is_minor_mode():
        return text
    blocked = ("酒吧", "夜店", "赌场")
    for w in blocked:
        text = text.replace(w, "**")
    return text


def privacy_policy_text() -> str:
    return (
        "AutoCityIntro 隐私说明：\n"
        "1. 会话与画像数据存储在本地 data/ 目录；\n"
        "2. 可通过 DELETE /api/privacy/data 删除您的 device_id 相关数据；\n"
        "3. GPS 坐标在日志中默认脱敏处理；\n"
        "4. 未成年人模式可通过 MINOR_MODE=true 启用。"
    )
