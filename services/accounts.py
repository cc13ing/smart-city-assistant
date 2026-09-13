"""简易账号与收藏（基于 device_id / account_token）"""
from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

import user_profile


def _sanitize_id(raw: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (raw or "default"))


def register_account(display_name: str = "", device_id: Optional[str] = None) -> Dict[str, Any]:
    did = device_id or user_profile.new_device_id()
    profile = user_profile.get_or_create_profile(did)
    token = profile.get("account_token") or secrets.token_urlsafe(16)
    profile["account_token"] = token
    profile["display_name"] = (display_name or profile.get("display_name") or "旅行者")[:40]
    profile.setdefault("favorite_trip_ids", [])
    profile.setdefault("favorite_poi_names", [])
    user_profile.save_profile(profile)
    return {
        "account_token": token,
        "device_id": did,
        "display_name": profile["display_name"],
    }


def resolve_owner_id(device_id: Optional[str], account_token: Optional[str] = None) -> str:
    """行程 owner：有 account_token 时用 token 作为跨设备 ID。"""
    if account_token:
        return _sanitize_id(account_token)
    return _sanitize_id(device_id or "default")


def get_profile_for_owner(device_id: Optional[str], account_token: Optional[str] = None) -> Dict[str, Any]:
    owner = resolve_owner_id(device_id, account_token)
    if account_token:
        p = user_profile.get_or_create_profile(owner)
        p.setdefault("account_token", account_token)
        if device_id:
            p["linked_device_id"] = device_id
        return p
    return user_profile.get_or_create_profile(device_id)


def get_device_prefs_profile(device_id: Optional[str]) -> Dict[str, Any]:
    """偏好、反馈、常去城市始终写入 device 画像（与 POST /api/feedback 一致）。"""
    return user_profile.get_or_create_profile(device_id)


def add_favorite_trip(profile: Dict[str, Any], trip_id: str) -> None:
    ids = profile.setdefault("favorite_trip_ids", [])
    if trip_id not in ids:
        ids.insert(0, trip_id)
    profile["favorite_trip_ids"] = ids[:30]


def add_favorite_poi(profile: Dict[str, Any], poi_name: str) -> None:
    if not poi_name:
        return
    names = profile.setdefault("favorite_poi_names", [])
    if poi_name not in names:
        names.insert(0, poi_name)
    profile["favorite_poi_names"] = names[:30]


def remove_favorite_poi(profile: Dict[str, Any], poi_name: str) -> None:
    if not poi_name:
        return
    names = profile.get("favorite_poi_names", [])
    profile["favorite_poi_names"] = [n for n in names if n != poi_name]


def remove_favorite_trip(profile: Dict[str, Any], trip_id: str) -> None:
    if not trip_id:
        return
    ids = profile.get("favorite_trip_ids", [])
    profile["favorite_trip_ids"] = [i for i in ids if i != trip_id]
