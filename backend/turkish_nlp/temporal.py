from __future__ import annotations

from datetime import date, timedelta

from backend.core.contracts import TemporalExpression


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


def resolve_temporal(text: str, today: date) -> list[TemporalExpression]:
    """Resolve common Turkish relative date expressions.

    Ranges are ``[start, end)``. ``today`` is injected so tests are
    deterministic and the result never depends on the wall clock.
    """
    found: list[TemporalExpression] = []
    this_month = _month_start(today)
    rules: list[tuple[str, date, date]] = [
        ("geçen ay", _add_months(this_month, -1), this_month),
        ("bu ay", this_month, _add_months(this_month, 1)),
        ("geçen yıl", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        ("bu yıl", date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        ("dün", today - timedelta(days=1), today),
        ("bugün", today, today + timedelta(days=1)),
        ("son 7 gün", today - timedelta(days=7), today + timedelta(days=1)),
        ("son 30 gün", today - timedelta(days=30), today + timedelta(days=1)),
        ("son 90 gün", today - timedelta(days=90), today + timedelta(days=1)),
    ]
    for phrase, start, end in rules:
        if phrase in text:
            found.append(TemporalExpression(text=phrase, start=start, end=end))
    return found
