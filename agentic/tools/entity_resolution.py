"""Reusable, conservative entity resolution for multilingual financial data.

The resolver is deliberately domain-agnostic. A tool supplies owner-scoped
candidates and their searchable labels; this module handles normalization,
partial first-name/alias matching, transliteration, typo tolerance, and
ambiguity without ever selecting through a close tie.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Generic, TypeVar
import unicodedata


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class EntityResolution(Generic[T]):
    match: T | None
    candidates: tuple[T, ...] = ()
    match_type: str = "not_found"


_ARABIC_TRANSLITERATION = str.maketrans(
    {
        "ا": "a", "أ": "a", "إ": "a", "آ": "a", "ٱ": "a",
        "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h",
        "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
        "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t",
        "ظ": "z", "ع": "", "غ": "gh", "ف": "f", "ق": "q",
        "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h",
        "ة": "a", "و": "u", "ؤ": "u", "ي": "i", "ى": "i",
        "ئ": "i", "ء": "",
    }
)


def normalize_entity_text(value: str) -> str:
    """Normalize harmless Unicode, Arabic, whitespace, and punctuation variants."""

    folded = unicodedata.normalize("NFKC", value).casefold().strip()
    folded = "".join(
        character
        for character in folded
        if not unicodedata.combining(character) and character != "ـ"
    )
    folded = folded.translate(
        str.maketrans(
            {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"}
        )
    )
    return " ".join(re.findall(r"[^\W_]+", folded, flags=re.UNICODE))


def multilingual_name_key(value: str) -> str:
    """Return a conservative Arabic/Latin consonant key for name comparison."""

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character != "ـ"
    )
    transliterated = normalized.translate(_ARABIC_TRANSLITERATION)
    latin = unicodedata.normalize("NFKD", transliterated)
    letters = "".join(character for character in latin if character.isascii() and character.isalpha())
    return "".join(character for character in letters if character not in "aeiouy")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in normalize_entity_text(value).split() if token)


def _same_token(left: str, right: str) -> bool:
    if left == right:
        return True
    left_key = multilingual_name_key(left)
    right_key = multilingual_name_key(right)
    return len(left_key) >= 2 and left_key == right_key


def _label_score(query: str, label: str, *, detachable_prefixes: frozenset[str]) -> float:
    query_tokens = _tokens(query)
    label_tokens = _tokens(label)
    if not query_tokens or not label_tokens:
        return 0.0

    query_first = query_tokens[0]
    label_first = label_tokens[0]
    if _same_token(query_first, label_first):
        return 0.96

    query_variants = [query_first]
    if len(query_first) >= 4 and query_first[0] in detachable_prefixes:
        query_variants.append(query_first[1:])

    best = 0.0
    label_key = multilingual_name_key(label_first)
    for query_variant in query_variants:
        normalized_ratio = SequenceMatcher(None, query_variant, label_first).ratio()
        query_key = multilingual_name_key(query_variant)
        key_ratio = (
            SequenceMatcher(None, query_key, label_key).ratio()
            if len(query_key) >= 2 and len(label_key) >= 2
            else 0.0
        )
        best = max(best, normalized_ratio, key_ratio)
    return best


def resolve_entity(
    query: str,
    candidates: Iterable[T],
    *,
    labels: Callable[[T], Iterable[str]],
    auto_match_threshold: float = 0.82,
    ambiguity_margin: float = 0.08,
    detachable_prefixes: frozenset[str] = frozenset({"ل", "ب"}),
    max_candidates: int = 20,
) -> EntityResolution[T]:
    """Resolve one unique candidate or return the close candidates for clarification."""

    materialized = tuple(candidates)
    normalized_query = normalize_entity_text(query)
    exact = tuple(
        candidate
        for candidate in materialized
        if normalized_query
        in {
            normalize_entity_text(label)
            for label in labels(candidate)
            if str(label).strip()
        }
    )
    if len(exact) == 1:
        return EntityResolution(match=exact[0], match_type="exact")
    if len(exact) > 1:
        return EntityResolution(match=None, candidates=exact[:max_candidates], match_type="ambiguous")

    scored = [
        (
            max(
                (
                    _label_score(query, label, detachable_prefixes=detachable_prefixes)
                    for label in labels(candidate)
                    if str(label).strip()
                ),
                default=0.0,
            ),
            candidate,
        )
        for candidate in materialized
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    strong = [(score, candidate) for score, candidate in scored if score >= auto_match_threshold]
    if len(strong) == 1:
        return EntityResolution(match=strong[0][1], match_type="unique_close")
    if len(strong) > 1:
        best_score = strong[0][0]
        close = tuple(candidate for score, candidate in strong if score >= best_score - ambiguity_margin)
        if len(close) == 1:
            return EntityResolution(match=close[0], match_type="unique_close")
        return EntityResolution(
            match=None,
            candidates=close[:max_candidates],
            match_type="ambiguous",
        )
    return EntityResolution(match=None)
