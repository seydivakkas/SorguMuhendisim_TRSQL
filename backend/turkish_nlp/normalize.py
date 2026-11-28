from __future__ import annotations

import re
import unicodedata

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_APOSTROPHES = re.compile(r"[’'`´]")
_SPACES = re.compile(r"\s+")


def tr_casefold(text: str) -> str:
    """Turkish-aware lowercase.

    Python's ``str.lower`` maps ``I`` to ``i`` and ``İ`` to ``i̇`` (with a
    combining dot), which is wrong for Turkish. Always use this function
    instead of ``.lower()`` on user text.
    """
    text = unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP)
    return text.lower()


def normalize_question(text: str) -> str:
    """Casefold, unify apostrophes (``Trabzon'daki`` → ``trabzon'daki``) and spaces."""
    text = tr_casefold(text)
    text = _APOSTROPHES.sub("'", text)
    return _SPACES.sub(" ", text).strip(" ?!.")


def strip_suffix(token: str) -> str:
    """Drop the case suffix after an apostrophe: ``trabzon'daki`` → ``trabzon``."""
    return token.split("'", 1)[0]
