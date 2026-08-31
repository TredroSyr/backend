"""One reading of `date_from` / `date_to` for the whole API.

Several screens filter documents by a date window — the invoice lists, the return
lists, the rep dashboard — and they must agree on what a window means, or the
same picker drives two screens to two different answers.

The rule that needs stating, because getting it wrong is silent: **a bare
`YYYY-MM-DD` bound covers that whole day.** Document dates are timestamps, so
comparing one against a plain date pins it to midnight, and `date_to=today` then
quietly drops everything written since. Widening the upper bound to the last
microsecond of the day is what makes an inclusive-looking filter inclusive.

A bound given as a full ISO 8601 timestamp is honoured exactly as written — a
client that wants "up to 14:00" is asking a different question and gets it.
"""

from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.domain import DomainError


def _aware(value: datetime) -> datetime:
    return value if timezone.is_aware(value) else timezone.make_aware(value)


def parse_bound(value: str, *, field: str, end_of_day: bool) -> datetime:
    """One end of a window, from either a date or a timestamp.

    `parse_date` is tried first on purpose: `parse_datetime` also accepts a bare
    date and hands back midnight, which would swallow the whole-day rule above
    before it ever ran.
    """
    day = parse_date(value)
    if day is not None:
        return _aware(datetime.combine(day, time.max if end_of_day else time.min))

    moment = parse_datetime(value)
    if moment is None:
        raise DomainError(
            "صيغة التاريخ غير صالحة",
            {field: ["Expected YYYY-MM-DD or an ISO 8601 timestamp."]},
        )

    return _aware(moment)


def parse_period(params) -> tuple[datetime | None, datetime | None]:
    """The window a client asked for; `(None, None)` means all time.

    `date=YYYY-MM-DD` is the shorthand a single-day picker sends and expands to
    that whole day. `date_from` / `date_to` are the general form and may be given
    independently — one open end is a valid window.

    No parameters means no window, which is what clearing a picker should do: the
    screen shows everything rather than a server-chosen default the client has no
    way to turn off.
    """
    day = params.get("date")
    if day:
        return (
            parse_bound(day, field="date", end_of_day=False),
            parse_bound(day, field="date", end_of_day=True),
        )

    date_from = params.get("date_from")
    date_to = params.get("date_to")

    return (
        parse_bound(date_from, field="date_from", end_of_day=False)
        if date_from
        else None,
        parse_bound(date_to, field="date_to", end_of_day=True) if date_to else None,
    )


def within_period(queryset, field: str, date_from, date_to):
    """Restrict a queryset to the window, if there is one."""
    if date_from:
        queryset = queryset.filter(**{f"{field}__gte": date_from})
    if date_to:
        queryset = queryset.filter(**{f"{field}__lte": date_to})
    return queryset


def filter_by_period(queryset, params, *, field: str = "date"):
    """`within_period` driven straight off a request's query params."""
    date_from, date_to = parse_period(params)
    return within_period(queryset, field, date_from, date_to)
