from __future__ import annotations

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent
_CACHE: dict[str, dict[str, str]] = {}
LANGS = ("ru", "uz", "en")


def clear_cache() -> None:
    _CACHE.clear()


def _load(lang: str) -> dict[str, str]:
    if lang not in _CACHE:
        path = LOCALES_DIR / f"{lang}.json"
        if not path.exists():
            path = LOCALES_DIR / "ru.json"
        with path.open(encoding="utf-8") as f:
            _CACHE[lang] = json.load(f)
    return _CACHE[lang]


def t(lang: str, key: str, **kwargs: object) -> str:
    data = _load(lang if lang in LANGS else "ru")
    text = data.get(key) or _load("ru").get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def all_t(key: str) -> frozenset[str]:
    """All translations of a key — for matching reply-keyboard buttons."""
    return frozenset(t(lang, key) for lang in LANGS)
