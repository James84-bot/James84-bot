"""Write audit events. Called by service functions inside their transaction,
so an action and its audit record are committed or rolled back together."""

from decimal import Decimal

from apps.core.logging import request_id_var

from .models import AuditEvent


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def record(
    *,
    organization,
    actor,
    action: str,
    summary: str,
    entity=None,
    changes: dict | None = None,
    flagged: bool = False,
    ip_address: str | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        organization=organization,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity._meta.label_lower if entity is not None else "",
        entity_id=str(entity.pk) if entity is not None else "",
        summary=summary[:300],
        changes=_jsonable(changes or {}),
        flagged=flagged,
        ip_address=ip_address,
        request_id=request_id_var.get(),
    )


def diff(instance, fields: list[str], new_values: dict) -> dict:
    """Return {field: [old, new]} for fields whose value changes."""
    out = {}
    for f in fields:
        if f in new_values:
            old = getattr(instance, f)
            new = new_values[f]
            if hasattr(old, "pk"):
                old = old.pk
            if hasattr(new, "pk"):
                new = new.pk
            if old != new:
                out[f] = [old, new]
    return out
