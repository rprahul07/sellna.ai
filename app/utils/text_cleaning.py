"""Text cleaning utilities shared across agents."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Remove excess whitespace, stray HTML entities, and control chars."""
    if not text:
        return ""
    # Decode common HTML entities that bs4 didn't convert
    replacements = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "",
        "\ufeff": "",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)

    # Strip control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/newlines into single space."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def deduplicate_list(items: list[str], case_sensitive: bool = False) -> list[str]:
    """Return list with duplicates removed, preserving original order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item if case_sensitive else item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncate text to a maximum character length."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def extract_sentences(text: str, max_sentences: int = 5) -> list[str]:
    """Split text into sentences and return up to max_sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 15][:max_sentences]
