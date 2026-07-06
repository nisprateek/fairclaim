"""UK-time date helpers and deterministic delivery-date extraction.

The CRA 2015 deadlines (30-day rejection, 6-month presumption, limitation
period) are computed from the date the goods were RECEIVED, in UK time.
Everything date-shaped is parsed and validated here in code — a model never
gets to guess a legal deadline. Used by both the intake interview (extracting
the delivery date from free text) and the MCP KB server (month arithmetic for
tier boundaries).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

MIN_DELIVERY_DATE = date(1900, 1, 1)
MIN_DELIVERY_DATE_ISO = MIN_DELIVERY_DATE.isoformat()

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORDINAL_RE = r"(?:st|nd|rd|th)?"
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_RELATIVE_AMOUNTS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty one": 21,
    "twenty-two": 22,
    "twenty two": 22,
    "twenty-three": 23,
    "twenty three": 23,
    "twenty-four": 24,
    "twenty four": 24,
}
_RELATIVE_AMOUNT_RE = "|".join(
    re.escape(value) for value in sorted(_RELATIVE_AMOUNTS, key=len, reverse=True)
)
_DELIVERY_DATE_CUES = (
    "arrived",
    "delivered",
    "delivery date",
    "delivery was",
    "received",
    "got it",
    "came",
    "collected",
    "picked up",
)
_PURCHASE_DATE_CUES = ("bought", "purchased")


def today_uk() -> date:
    return datetime.now(UK_TZ).date()


def add_months(d: date, months: int) -> date:
    """Calendar-month arithmetic, clamping to the target month's last day."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _full_year(raw: str | None, today: date) -> int:
    if not raw:
        return today.year
    year = int(raw)
    return 2000 + year if year < 100 else year


def _relative_amount(raw: str) -> int:
    raw = raw.strip().lower()
    return int(raw) if raw.isdigit() else _RELATIVE_AMOUNTS[raw]


def _is_valid_delivery_date(parsed: date, today: date) -> bool:
    return MIN_DELIVERY_DATE <= parsed <= today


def _date_or_none(year: int, month: int, day: int, today: date, *, explicit_year: bool) -> date | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed > today and not explicit_year:
        try:
            parsed = date(year - 1, month, day)
        except ValueError:
            return None
    if parsed > today:
        return None
    if not _is_valid_delivery_date(parsed, today):
        return None
    return parsed


def _date_mentions(text: str, today: date) -> list[tuple[int, int, str]]:
    mentions: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []

    def add(match: re.Match[str], parsed: date | None) -> None:
        if not parsed:
            return
        if not _is_valid_delivery_date(parsed, today):
            return
        span = match.span()
        if any(max(span[0], start) < min(span[1], end) for start, end in occupied):
            return
        occupied.append(span)
        mentions.append((span[0], span[1], parsed.isoformat()))

    for match in re.finditer(r"(?<![\d/-])((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})(?![\d/-])", text):
        add(
            match,
            _date_or_none(int(match[1]), int(match[2]), int(match[3]), today, explicit_year=True),
        )

    for match in re.finditer(r"(?<![\d/-])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?![\d/-])", text):
        explicit_year = bool(match[3])
        add(
            match,
            _date_or_none(
                _full_year(match[3], today),
                int(match[2]),
                int(match[1]),
                today,
                explicit_year=explicit_year,
            ),
        )

    for match in re.finditer(rf"\b(\d{{1,2}}){_ORDINAL_RE}\s+({_MONTH_RE})(?:\s+(\d{{2,4}}))?\b", text, re.I):
        explicit_year = bool(match[3])
        add(
            match,
            _date_or_none(
                _full_year(match[3], today),
                _MONTHS[match[2].lower()],
                int(match[1]),
                today,
                explicit_year=explicit_year,
            ),
        )

    for match in re.finditer(rf"\b({_MONTH_RE})\s+(\d{{1,2}}){_ORDINAL_RE}(?:,?\s+(\d{{2,4}}))?\b", text, re.I):
        explicit_year = bool(match[3])
        add(
            match,
            _date_or_none(
                _full_year(match[3], today),
                _MONTHS[match[1].lower()],
                int(match[2]),
                today,
                explicit_year=explicit_year,
            ),
        )

    relative = re.compile(
        r"\b(?:about|around|roughly|approximately|approx\.?)?\s*"
        rf"(\d+|{_RELATIVE_AMOUNT_RE})\s+"
        r"(day|days|week|weeks|fortnight|fortnights|month|months|year|years)\s+ago\b",
        re.I,
    )
    for match in relative.finditer(text):
        amount = _relative_amount(match[1])
        unit = match[2].lower()
        if unit.startswith("month"):
            parsed = add_months(today, -amount)
        elif unit.startswith("year"):
            parsed = add_months(today, -(amount * 12))
        else:
            multiplier = 14 if unit.startswith("fortnight") else 7 if unit.startswith("week") else 1
            parsed = today - timedelta(days=amount * multiplier)
        add(match, parsed)

    for match in re.finditer(r"\byesterday\b", text, re.I):
        add(match, today - timedelta(days=1))
    for match in re.finditer(r"\btoday\b", text, re.I):
        add(match, today)
    for match in re.finditer(r"\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.I):
        target = _WEEKDAYS[match[1].lower()]
        days_back = (today.weekday() - target) % 7 or 7
        add(match, today - timedelta(days=days_back))

    return sorted(mentions, key=lambda item: item[0])


def extract_delivery_date(
    text: str | None,
    *,
    today: date | None = None,
    allow_contextless: bool = False,
) -> str | None:
    """Extract the received/delivered date as ISO YYYY-MM-DD.

    Opening stories need a cue so we do not mistake a returns-policy window
    for the delivery date. Direct date-field answers can be contextless.
    """
    if not text:
        return None
    today = today or today_uk()
    mentions = _date_mentions(str(text), today)
    if not mentions:
        return None
    lowered = str(text).lower()
    candidates: list[tuple[int, int, str]] = []
    for start, end, iso in mentions:
        preceding_context = lowered[max(0, start - 60) : end]
        if any(cue in preceding_context for cue in _DELIVERY_DATE_CUES):
            candidates.append((0, start, iso))
        elif any(cue in preceding_context for cue in _PURCHASE_DATE_CUES):
            candidates.append((1, start, iso))
        elif allow_contextless:
            candidates.append((2, start, iso))
    if not candidates:
        return None
    return min(candidates)[2]
