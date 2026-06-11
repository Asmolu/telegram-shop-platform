from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches

SEARCH_PRIORITY_DEFAULT = 2
SEARCH_PRIORITY_VALUES = (1, 2, 3)
SEARCH_TRIGRAM_SIMILARITY_THRESHOLD = 0.2
SEARCH_ALIAS_MAX_LENGTH = 2000

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_CYRILLIC_RE = re.compile(r"[а-я]", re.IGNORECASE)

COLOR_SYNONYMS: dict[str, tuple[str, ...]] = {
    "белый": ("white",),
    "белая": ("white",),
    "белое": ("white",),
    "белые": ("white",),
    "черный": ("black",),
    "черная": ("black",),
    "черное": ("black",),
    "черные": ("black",),
    "красный": ("red",),
    "красная": ("red",),
    "красное": ("red",),
    "красные": ("red",),
    "синий": ("blue",),
    "синяя": ("blue",),
    "синее": ("blue",),
    "синие": ("blue",),
    "голубой": ("light blue", "blue"),
    "голубая": ("light blue", "blue"),
    "голубое": ("light blue", "blue"),
    "голубые": ("light blue", "blue"),
    "зеленый": ("green",),
    "зеленая": ("green",),
    "зеленое": ("green",),
    "зеленые": ("green",),
    "желтый": ("yellow",),
    "желтая": ("yellow",),
    "желтое": ("yellow",),
    "желтые": ("yellow",),
    "серый": ("gray", "grey"),
    "серая": ("gray", "grey"),
    "серое": ("gray", "grey"),
    "серые": ("gray", "grey"),
    "бежевый": ("beige",),
    "бежевая": ("beige",),
    "бежевое": ("beige",),
    "бежевые": ("beige",),
    "коричневый": ("brown",),
    "коричневая": ("brown",),
    "коричневое": ("brown",),
    "коричневые": ("brown",),
    "розовый": ("pink",),
    "розовая": ("pink",),
    "розовое": ("pink",),
    "розовые": ("pink",),
    "оранжевый": ("orange",),
    "оранжевая": ("orange",),
    "оранжевое": ("orange",),
    "оранжевые": ("orange",),
    "фиолетовый": ("purple",),
    "фиолетовая": ("purple",),
    "фиолетовое": ("purple",),
    "фиолетовые": ("purple",),
    "бордовый": ("burgundy",),
    "бордовая": ("burgundy",),
    "бордовое": ("burgundy",),
    "бордовые": ("burgundy",),
    "молочный": ("milk", "cream", "white"),
    "молочная": ("milk", "cream", "white"),
    "молочное": ("milk", "cream", "white"),
    "молочные": ("milk", "cream", "white"),
    "кремовый": ("cream",),
    "кремовая": ("cream",),
    "кремовое": ("cream",),
    "кремовые": ("cream",),
    "хаки": ("khaki",),
}
LATIN_COLOR_TERMS = frozenset(term for terms in COLOR_SYNONYMS.values() for term in terms)


@dataclass(frozen=True)
class SearchToken:
    value: str
    color_terms: tuple[str, ...] = ()

    @property
    def is_numeric_size(self) -> bool:
        return self.value.isascii() and self.value.isdigit()


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


def tokenize_search_query(value: str | None) -> tuple[SearchToken, ...]:
    normalized = normalize_search_text(value)
    if not normalized:
        return ()
    return tuple(
        SearchToken(value=token, color_terms=_color_terms_for_token(token))
        for token in _TOKEN_RE.findall(normalized)
    )


def expand_color_query(value: str | None) -> tuple[str, ...]:
    normalized = normalize_search_text(value)
    if not normalized:
        return ()
    exact = COLOR_SYNONYMS.get(normalized)
    if exact:
        return exact
    tokens = _TOKEN_RE.findall(normalized)
    expanded = [term for token in tokens for term in _color_terms_for_token(token)]
    return tuple(dict.fromkeys(expanded or [normalized]))


def _color_terms_for_token(token: str) -> tuple[str, ...]:
    exact = COLOR_SYNONYMS.get(token)
    if exact:
        return exact
    if token in LATIN_COLOR_TERMS:
        return (token,)
    if not _CYRILLIC_RE.search(token) or len(token) < 4:
        return ()
    match = get_close_matches(token, COLOR_SYNONYMS, n=1, cutoff=0.78)
    return COLOR_SYNONYMS[match[0]] if match else ()


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
