from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from backend.core.contracts import TemporalExpression
from backend.turkish_nlp.normalize import normalize_question

_MONTH_MAP: dict[str, int] = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}

_NUMBER_WORDS: dict[str, int] = {
    "bir": 1,
    "iki": 2,
    "üç": 3,
    "dört": 4,
    "beş": 5,
    "altı": 6,
    "yedi": 7,
    "sekiz": 8,
    "dokuz": 9,
    "on": 10,
    "on bir": 11,
    "on iki": 12,
    "on beş": 15,
    "yirmi": 20,
    "otuz": 30,
    "kırk": 40,
    "elli": 50,
    "altmış": 60,
    "doksan": 90,
    "yüz": 100,
}

_ORDINAL_QUARTER: dict[str, int] = {
    "1": 1,
    "1.": 1,
    "birinci": 1,
    "ilk": 1,
    "2": 2,
    "2.": 2,
    "ikinci": 2,
    "3": 3,
    "3.": 3,
    "üçüncü": 3,
    "4": 4,
    "4.": 4,
    "dördüncü": 4,
    "son": 4,
}

_ORDINAL_HALF: dict[str, int] = {
    "1": 1,
    "1.": 1,
    "birinci": 1,
    "ilk": 1,
    "2": 2,
    "2.": 2,
    "ikinci": 2,
}

_DATE_RANGE_RE = re.compile(
    r"\b(?P<d1>\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\s*"
    r"(?:-|–|—|ile)\s*"
    r"(?P<d2>\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})"
    r"(?:\s*(?:arası|arasında|arasındaki|tarihleri arası))?\b"
)
_ISO_DATE_RE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_TR_DATE_RE = re.compile(r"\b(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})\b")

_SAME_PERIOD_LAST_YEAR_RE = re.compile(
    r"\b(?:geçen|önceki)\s+(?:yıl|sene)(?:ın|nın|in|nin)?\s+aynı\s+"
    r"(?:dönemi(?:ni|ne|nde|nden|nin)?|ayı(?:nı|na|nda|ndan|nın)?|dönem|ay)\b"
)

_YTD_RE = re.compile(r"\b(?:yıl\s*başından\s+bugüne|sene\s*başından\s+bugüne)\b")
_MTD_RE = re.compile(r"\b(?:bu\s+)?ay\s*başından\s+bugüne\b")

_QUARTER_RE = re.compile(
    r"\b(?:(?P<pre_year>\d{4}|geçen\s+yıl|bu\s+yıl|gelecek\s+yıl|önümüzdeki\s+yıl)"
    r"(?:'?(?:ın|in|un|ün|nın|nin|da|de|ta|te)|\s+yılı(?:nın)?|\s+senesi(?:nin)?)?\s+)?"
    r"(?P<ord>1\.|2\.|3\.|4\.|birinci|ikinci|üçüncü|dördüncü|son)\s+çeyre(?:k|ği|ğinde|kte|kten|ğiyle|kler)?"
    r"(?:\s+(?P<post_year>\d{4}))?\b"
)
_Q_SHORT_RE = re.compile(r"\b(?:(?P<pre_year>\d{4})\s+)?q(?P<q>[1-4])(?:\s+(?P<post_year>\d{4}))?\b")

_HALF_RE = re.compile(
    r"\b(?:(?P<pre_year>\d{4}|geçen\s+yıl|bu\s+yıl|gelecek\s+yıl|önümüzdeki\s+yıl)"
    r"(?:'?(?:ın|in|un|ün|nın|nin)|\s+yılı(?:nın)?)?\s+)?"
    r"(?P<ord>1\.|2\.|birinci|ikinci|ilk)\s+yarı(?:yıl)?(?:ı|ında|ındaki)?\b"
)

_MONTH_NAMES_ALT = "|".join(_MONTH_MAP.keys())
# Note: avoid matching ``aralığı`` (meaning "range/interval") as December!
_MONTH_RE = re.compile(
    rf"\b(?:(?P<pre_year>\d{{4}}|geçen\s+yıl|bu\s+yıl|gelecek\s+yıl|önümüzdeki\s+yıl)"
    rf"(?:'?(?:ın|in|un|ün|nın|nin)|\s+yılı(?:nın)?|\s+senesi(?:nin)?)?\s+)?"
    rf"(?P<month>{_MONTH_NAMES_ALT})"
    rf"(?:'?(?:da|de|ta|te|dan|den|tan|ten|daki|deki|taki|teki|a|e|ın|in|un|ün|yi|yı)?)?"
    rf"(?:\s+ay(?:ı|ında|ının|ındaki|ına|ından)?)?"
    rf"(?:\s+(?P<post_year>\d{{4}}))?\b"
)

_NUM_WORDS_ALT = "|".join(sorted(_NUMBER_WORDS.keys(), key=len, reverse=True))
_LAST_N_RE = re.compile(
    rf"\bson\s+(?P<n>\d+|{_NUM_WORDS_ALT})\s+(?P<unit>gün|hafta|ay|yıl|sene)"
    r"(?:lık|lik|luk|lük|ün|un|ın|in|nün|nun|nın|nin|de|da|te|ta|den|dan|ten|tan|e|a|ki)?\b"
)
_LAST_SINGLE_RE = re.compile(
    r"\bson\s+(?P<unit>hafta|ay|yıl|sene)"
    r"(?:nın|nin|nun|nün|ın|in|un|ün|da|de|dan|den|ya|ye|a|e|ki)?\b"
)

_EXPLICIT_YEAR_RE = re.compile(
    r"\b(?P<y>19\d{2}|20\d{2}|2100)"
    r"(?:\s*(?:yılı(?:nda|nın|ndaki|na|ndan)?|senesi(?:nde|nin)?)|"
    r"'?(?:da|de|ta|te|dan|den|tan|ten|daki|deki|ın|in|un|ün))\b"
)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


def _shift_months_preserve_day(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    year, month = idx // 12, idx % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_day))


def _shift_years(d: date, years: int) -> date:
    year = d.year + years
    max_day = calendar.monthrange(year, d.month)[1]
    return date(year, d.month, min(d.day, max_day))


def _resolve_year_ref(ref: str | None, today: date) -> int:
    if not ref:
        return today.year
    ref = ref.strip()
    if ref.isdigit():
        return int(ref)
    if "geçen" in ref:
        return today.year - 1
    if "gelecek" in ref or "önümüzdeki" in ref:
        return today.year + 1
    return today.year


def _parse_single_date(raw: str) -> date | None:
    try:
        if "-" in raw:
            y_s, m_s, d_s = raw.split("-")
            return date(int(y_s), int(m_s), int(d_s))
        d_s, m_s, y_s = raw.split(".")
        return date(int(y_s), int(m_s), int(d_s))
    except ValueError:
        return None


def _parse_count(raw: str) -> int | None:
    if raw.isdigit():
        val = int(raw)
        return val if 1 <= val <= 36_500 else None
    return _NUMBER_WORDS.get(raw)


class _SpanCollector:
    """Collect non-overlapping temporal matches sorted by appearance."""

    def __init__(self) -> None:
        self._claimed: list[tuple[int, int]] = []
        self._items: list[tuple[int, TemporalExpression]] = []

    def overlaps(self, start: int, end: int) -> bool:
        return any(not (end <= cs or start >= ce) for cs, ce in self._claimed)

    def add(self, pos_start: int, pos_end: int, expr: TemporalExpression) -> bool:
        if self.overlaps(pos_start, pos_end):
            return False
        self._claimed.append((pos_start, pos_end))
        self._items.append((pos_start, expr))
        return True

    def results(self) -> list[TemporalExpression]:
        return [expr for _, expr in sorted(self._items, key=lambda pair: pair[0])]


def resolve_temporal(text: str, today: date) -> list[TemporalExpression]:
    """Resolve Turkish relative and explicit date expressions into ``[start, end)``.

    ``today`` is injected so tests are deterministic and never depend on the
    wall clock.
    """
    norm = normalize_question(text)
    collector = _SpanCollector()

    this_month = _month_start(today)
    week_start = today - timedelta(days=today.weekday())
    q_start = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)

    # 1. Explicit date ranges
    for m in _DATE_RANGE_RE.finditer(norm):
        d1 = _parse_single_date(m.group("d1"))
        d2 = _parse_single_date(m.group("d2"))
        if d1 is not None and d2 is not None and d1 <= d2:
            collector.add(
                m.start(),
                m.end(),
                TemporalExpression(text=m.group(0), start=d1, end=d2 + timedelta(days=1)),
            )

    # 2. Explicit single dates
    for pattern in (_ISO_DATE_RE, _TR_DATE_RE):
        for m in pattern.finditer(norm):
            d = _parse_single_date(m.group(0))
            if d is not None:
                collector.add(
                    m.start(),
                    m.end(),
                    TemporalExpression(text=m.group(0), start=d, end=d + timedelta(days=1)),
                )

    # 3. Same period last year (remember span so we can align with companion period)
    same_period_matches = list(_SAME_PERIOD_LAST_YEAR_RE.finditer(norm))
    for m in same_period_matches:
        # Claim span immediately so "geçen yıl" doesn't double-match inside it.
        collector._claimed.append((m.start(), m.end()))

    # 4. YTD / MTD
    for m in _YTD_RE.finditer(norm):
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=m.group(0), start=date(today.year, 1, 1), end=today + timedelta(days=1)),
        )
    for m in _MTD_RE.finditer(norm):
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=m.group(0), start=this_month, end=today + timedelta(days=1)),
        )

    # 5. Quarters (explicit/relative year + ordinal)
    for m in _QUARTER_RE.finditer(norm):
        q_num = _ORDINAL_QUARTER[m.group("ord")]
        year = _resolve_year_ref(m.group("pre_year") or m.group("post_year"), today)
        qs = date(year, (q_num - 1) * 3 + 1, 1)
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=m.group(0), start=qs, end=_add_months(qs, 3)),
        )
    for m in _Q_SHORT_RE.finditer(norm):
        q_num = int(m.group("q"))
        year = _resolve_year_ref(m.group("pre_year") or m.group("post_year"), today)
        qs = date(year, (q_num - 1) * 3 + 1, 1)
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=m.group(0), start=qs, end=_add_months(qs, 3)),
        )

    # 6. Half-years
    for m in _HALF_RE.finditer(norm):
        h_num = _ORDINAL_HALF[m.group("ord")]
        year = _resolve_year_ref(m.group("pre_year"), today)
        hs = date(year, 1 if h_num == 1 else 7, 1)
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=m.group(0), start=hs, end=_add_months(hs, 6)),
        )

    # 7. Turkish months (with optional pre/post year)
    for m in _MONTH_RE.finditer(norm):
        raw = m.group(0)
        # Skip "aralığı" / "aralığın" (Turkish noun "aralık" = range/interval)
        if m.group("month") == "aralık" and raw.startswith("aralığ"):
            continue
        month_num = _MONTH_MAP[m.group("month")]
        year = _resolve_year_ref(m.group("pre_year") or m.group("post_year"), today)
        ms = date(year, month_num, 1)
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(text=raw, start=ms, end=_add_months(ms, 1)),
        )

    # 8. "son N gün/hafta/ay/yıl" & "son hafta/ay/yıl"
    for m in _LAST_N_RE.finditer(norm):
        count = _parse_count(m.group("n"))
        if count is None:
            continue
        unit = m.group("unit")
        end = today + timedelta(days=1)
        if unit == "gün":
            start = today - timedelta(days=count)
        elif unit == "hafta":
            start = today - timedelta(weeks=count)
        elif unit == "ay":
            start = _shift_months_preserve_day(today, -count)
        else:
            start = _shift_years(today, -count)
        collector.add(m.start(), m.end(), TemporalExpression(text=m.group(0), start=start, end=end))

    for m in _LAST_SINGLE_RE.finditer(norm):
        unit = m.group("unit")
        end = today + timedelta(days=1)
        if unit == "hafta":
            start = today - timedelta(weeks=1)
        elif unit == "ay":
            start = _shift_months_preserve_day(today, -1)
        else:
            start = _shift_years(today, -1)
        collector.add(m.start(), m.end(), TemporalExpression(text=m.group(0), start=start, end=end))

    # 9. Fixed relative phrases (ordered longest/most-specific first)
    fixed_rules: tuple[tuple[str, date, date], ...] = (
        ("evvelsi gün", today - timedelta(days=2), today - timedelta(days=1)),
        ("önceki gün", today - timedelta(days=2), today - timedelta(days=1)),
        ("geçen hafta sonu", week_start - timedelta(days=2), week_start),
        ("bu hafta sonu", week_start + timedelta(days=5), week_start + timedelta(days=7)),
        ("hafta sonu", week_start + timedelta(days=5), week_start + timedelta(days=7)),
        ("geçen hafta", week_start - timedelta(days=7), week_start),
        ("geçtiğimiz hafta", week_start - timedelta(days=7), week_start),
        ("önceki hafta", week_start - timedelta(days=7), week_start),
        ("gelecek hafta", week_start + timedelta(days=7), week_start + timedelta(days=14)),
        ("önümüzdeki hafta", week_start + timedelta(days=7), week_start + timedelta(days=14)),
        ("bu hafta", week_start, week_start + timedelta(days=7)),
        ("geçen ay", _add_months(this_month, -1), this_month),
        ("geçtiğimiz ay", _add_months(this_month, -1), this_month),
        ("önceki ay", _add_months(this_month, -1), this_month),
        ("gelecek ay", _add_months(this_month, 1), _add_months(this_month, 2)),
        ("önümüzdeki ay", _add_months(this_month, 1), _add_months(this_month, 2)),
        ("bu ay", this_month, _add_months(this_month, 1)),
        ("cari ay", this_month, _add_months(this_month, 1)),
        ("geçen çeyrek", _add_months(q_start, -3), q_start),
        ("geçtiğimiz çeyrek", _add_months(q_start, -3), q_start),
        ("önceki çeyrek", _add_months(q_start, -3), q_start),
        ("gelecek çeyrek", _add_months(q_start, 3), _add_months(q_start, 6)),
        ("önümüzdeki çeyrek", _add_months(q_start, 3), _add_months(q_start, 6)),
        ("bu çeyrek", q_start, _add_months(q_start, 3)),
        ("geçen yıl", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        ("geçen sene", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        ("geçtiğimiz yıl", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        ("önceki yıl", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        ("gelecek yıl", date(today.year + 1, 1, 1), date(today.year + 2, 1, 1)),
        ("önümüzdeki yıl", date(today.year + 1, 1, 1), date(today.year + 2, 1, 1)),
        ("gelecek sene", date(today.year + 1, 1, 1), date(today.year + 2, 1, 1)),
        ("bu yıl", date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        ("bu sene", date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        ("cari yıl", date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        ("bugün", today, today + timedelta(days=1)),
        ("dün", today - timedelta(days=1), today),
        ("yarın", today + timedelta(days=1), today + timedelta(days=2)),
    )
    fixed_suffix = (
        r"(?:'?(?:ki|kü|kı|ku|daki|deki|taki|teki|ın|in|un|ün|"
        r"nın|nin|nun|nün|da|de|ta|te|dan|den|tan|ten|a|e|ya|ye))?"
    )
    for phrase, start, end in fixed_rules:
        pattern = re.compile(rf"\b{re.escape(phrase)}{fixed_suffix}\b")
        for m in pattern.finditer(norm):
            collector.add(m.start(), m.end(), TemporalExpression(text=phrase, start=start, end=end))

    # 10. Explicit year expressions (e.g. "2025 yılı", "2024'te")
    for m in _EXPLICIT_YEAR_RE.finditer(norm):
        year = int(m.group("y"))
        collector.add(
            m.start(),
            m.end(),
            TemporalExpression(
                text=m.group(0),
                start=date(year, 1, 1),
                end=date(year + 1, 1, 1),
            ),
        )

    # Finalize "geçen yılın aynı dönemi" relative to a companion expression if present,
    # otherwise the same calendar month one year ago.
    companion = next(iter(collector._items), None)
    for m in same_period_matches:
        if companion is not None and companion[1].start is not None and companion[1].end is not None:
            sp_start = _shift_years(companion[1].start, -1)
            sp_end = _shift_years(companion[1].end, -1)
        else:
            last_yr_month = _add_months(this_month, -12)
            sp_start = last_yr_month
            sp_end = _add_months(last_yr_month, 1)
        collector._items.append(
            (m.start(), TemporalExpression(text="geçen yılın aynı dönemi", start=sp_start, end=sp_end))
        )

    return collector.results()
