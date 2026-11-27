from __future__ import annotations

import re

# Order matters: longer / more specific patterns first.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE), "[IBAN]"),
    (re.compile(r"(?i)\b(?:password|parola|şifre|secret|token|api[_-]?key)\s*[:=]\s*\S+"), "[SECRET]"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|xox[abp])[-_][A-Za-z0-9_-]{10,}\b"), "[SECRET]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"\b[1-9]\d{10}\b"), "[TCKN]"),
    (re.compile(r"(?:\+90|0)?\s?5\d{2}\s?\d{3}\s?\d{2}\s?\d{2}\b"), "[TELEFON]"),
    (re.compile(r"\b(?:\d[ -]?){15,16}\b"), "[KART]"),
)


def mask_sensitive(text: str) -> str:
    """Mask personal / secret data before logging (KVKK, docs/security)."""
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text
