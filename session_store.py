"""会话元数据持久化（UI 列表、GPS、展示用 conversation_history）"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(os.getenv("SESSION_DATA_DIR", "data/sessions"))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _session_path(session_id: str) -> Path:
    return DATA_DIR / f"{session_id}.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def create_session(
    session_id: Optional[str] = None,
    title: str = "新对话",
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_data_dir()
    sid = session_id or str(uuid.uuid4())
    session = {
        "session_id": sid,
        "title": title,
        "device_id": device_id or "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "conversation_history": [],
        "tool_call_history": [],
    }
    save_session(session)
    return session


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_or_create_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    if session_id:
        existing = get_session(session_id)
        if existing:
            return existing
        return create_session(session_id)
    return create_session()


def save_session(session: Dict[str, Any]) -> None:
    ensure_data_dir()
    session["updated_at"] = _now_iso()
    path = _session_path(session["session_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def list_sessions() -> List[Dict[str, Any]]:
    ensure_data_dir()
    sessions = []
    for path in DATA_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data.get("session_id", path.stem),
                "title": data.get("title", "未命名"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("conversation_history", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    deleted = False
    if path.exists():
        path.unlink()
        deleted = True
    try:
        from graph.checkpoints import delete_checkpoint_thread

        delete_checkpoint_thread(session_id)
        deleted = True
    except Exception:
        pass
    return deleted
