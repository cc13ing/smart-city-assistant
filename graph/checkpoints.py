"""LangGraph Checkpoint 持久化（SqliteSaver，thread_id = session_id）"""
import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

CHECKPOINT_DIR = Path(os.getenv("CHECKPOINT_DATA_DIR", "data"))
CHECKPOINT_DB = CHECKPOINT_DIR / "checkpoints.db"

_saver: SqliteSaver | None = None


def get_checkpointer() -> SqliteSaver:
    global _saver
    if _saver is None:
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        _saver = SqliteSaver(conn)
    return _saver


def delete_checkpoint_thread(thread_id: str) -> None:
    """删除会话对应的 LangGraph checkpoint 线程。"""
    if not thread_id:
        return
    try:
        get_checkpointer().delete_thread(thread_id)
    except Exception:
        pass
