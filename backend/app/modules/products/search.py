from __future__ import annotations

import re

SEARCH_PRIORITY_DEFAULT = 2
SEARCH_PRIORITY_VALUES = (1, 2, 3)
SEARCH_TRIGRAM_SIMILARITY_THRESHOLD = 0.2
SEARCH_ALIAS_MAX_LENGTH = 2000

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


def sanitize_search_query(value: str | None, *, max_length: int = 255) -> str | None:
    if value is None:
        return None
    sanitized = _CONTROL_CHARS_RE.sub(" ", value)
    sanitized = _WHITESPACE_RE.sub(" ", sanitized).strip()
    if not sanitized:
        return None
    return sanitized[:max_length]


def normalize_search_text(value: str | None) -> str | None:
    sanitized = sanitize_search_query(value, max_length=SEARCH_ALIAS_MAX_LENGTH)
    if sanitized is None:
        return None
    return sanitized.casefold().replace("ё", "е")


def normalize_search_aliases(value: str | None) -> str | None:
    if value is None:
        return None
    parts = [
        part.strip()
        for raw_line in value.replace(",", "\n").splitlines()
        for part in raw_line.split(",")
        if part.strip()
    ]
    if not parts:
        return None
    return "\n".join(dict.fromkeys(parts))[:SEARCH_ALIAS_MAX_LENGTH]


def search_text_matches_query(text: str | None, query: str | None) -> bool:
    normalized_query = normalize_search_text(query)
    normalized_text = normalize_search_text(text)
    if not normalized_query or not normalized_text:
        return False
    if normalized_query in normalized_text:
        return True
    return any(
        _normalized_similarity(token, normalized_query) >= 0.74
        for token in _TOKEN_RE.findall(normalized_text)
    )


def _normalized_similarity(left: str, right: str) -> float:
    distance = _levenshtein_distance(left, right)
    longest = max(len(left), len(right))
    if longest == 0:
        return 1.0
    return 1 - (distance / longest)


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]
