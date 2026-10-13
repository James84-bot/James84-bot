"""Business dates are interpreted in the organisation's time zone, so a
report "for 31 March" in Nairobi covers 00:00–23:59 EAT, not UTC."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import ValidationError


def parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "Use the format YYYY-MM-DD."}) from exc


def org_tz(org) -> ZoneInfo:
    return ZoneInfo(org.timezone)


def org_today(org) -> date:
    return timezone.now().astimezone(org_tz(org)).date()


def day_start(org, d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=org_tz(org))


def filter_created_between(qs, org, params, field: str = "created_at"):
    """Apply ?date_from=&date_to= (inclusive, organisation local dates)."""
    d_from = parse_date(params.get("date_from"), "date_from")
    d_to = parse_date(params.get("date_to"), "date_to")
    if d_from and d_to and d_from > d_to:
        raise ValidationError({"date_to": "The end date is before the start date."})
    if d_from:
        qs = qs.filter(**{f"{field}__gte": day_start(org, d_from)})
    if d_to:
        qs = qs.filter(**{f"{field}__lt": day_start(org, d_to + timedelta(days=1))})
    return qs
