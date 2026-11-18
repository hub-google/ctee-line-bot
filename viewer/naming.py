"""Consistent readable filenames for source-preserving newspaper archives."""
from __future__ import annotations

import re
from pathlib import Path

_SEPARATOR = re.compile(r"[,，、]+")
_UNSAFE = re.compile(r'[\\/:*?"<>|#%\x00-\x1f\x7f]+')
_VALID_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def matched_keywords(value: str) -> list[str]:
    """Keep ALL matched terms once, in their original order."""
    seen: set[str] = set()
    words: list[str] = []
    for raw in _SEPARATOR.split(value or ""):
        term = _UNSAFE.sub("", raw).strip().strip(". ")
        if term and term not in seen:
            seen.add(term)
            words.append(term)
    return words


def named_original(date: str, index: int, matched: str, suffix: str) -> str:
    """YYYYMMDD_01_關鍵字1、關鍵字2.jpg, keeping original image extension."""
    if not _VALID_DATE.fullmatch(date) or index < 1:
        raise ValueError("Invalid newspaper date or clipping index")
    ext = suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise ValueError("Unsupported original file suffix: " + ext)
    label = "、".join(matched_keywords(matched)) or "未分類"
    name = f"{date.replace('-', '')}_{index:02d}_{label}{ext}"
    if len(name.encode("utf-8")) > 240:
        raise ValueError("Matched keywords too long for a safe image filename")
    if Path(name).name != name:
        raise ValueError("Unsafe image filename")
    return name
