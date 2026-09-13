"""将 Markdown / 富文本转为适合 TTS 朗读的纯文本"""
import re

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]",
    flags=re.UNICODE,
)


def to_speech_text(text: str, max_len: int = 500) -> str:
    if not text:
        return ""
    s = str(text)

    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^>\s?", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+[.)．、]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^-{3,}\s*$", " ", s, flags=re.MULTILINE)
    s = re.sub(r"^\*{3,}\s*$", " ", s, flags=re.MULTILINE)
    s = re.sub(r"^\|?[\s:|-]+\|?\s*$", " ", s, flags=re.MULTILINE)
    s = s.replace("|", "，")
    s = re.sub(r"[#*_~`>|]", " ", s)
    s = re.sub(r"\\([\\`*_{}\[\]()#+.!-])", r"\1", s)
    s = _EMOJI_RE.sub(" ", s)
    s = s.replace("→", "到").replace("·", "，").replace("…", "。")
    s = re.sub(r"[^\S\n]+", " ", s)
    s = re.sub(r"\n+", "，", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"[，,。．；;：:\s]{2,}", "，", s)
    return s.strip()[:max_len]
