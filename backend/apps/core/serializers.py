"""Serializer helpers that keep every reference inside the caller's organisation."""

from rest_framework import serializers


class OrgRelatedField(serializers.PrimaryKeyRelatedField):
    """A foreign-key field that only accepts records from the current
    organisation. An ID from another organisation is reported as not found,
    exactly like an ID that does not exist."""

    default_error_messages = {
        "does_not_exist": "Not found. Choose an existing record.",
        "incorrect_type": "Invalid ID.",
    }

    def __init__(self, model, extra_filter=None, **kwargs):
        self.model = model
        self.extra_filter = extra_filter or {}
        kwargs.setdefault("queryset", model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        org = self.context.get("organization")
        if org is None:
            return self.model.objects.none()
        return self.model.objects.filter(organization=org, **self.extra_filter)

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except Exception as exc:
            # Malformed UUIDs raise ValidationError from Django; normalise.
            if isinstance(exc, serializers.ValidationError):
                raise
            self.fail("incorrect_type", data_type=type(data).__name__)


class UniqueInOrgMixin:
    """Case-insensitive uniqueness within the organisation, reported as a
    field error instead of a database IntegrityError.

    Declare `unique_in_org = {"field": "message"}` on the serializer.
    """

    unique_in_org: dict[str, str] = {}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        org = self.context.get("organization")
        model = self.Meta.model
        errors = {}
        for field, message in self.unique_in_org.items():
            if field not in attrs:
                continue
            qs = model.objects.filter(organization=org, **{f"{field}__iexact": attrs[field]})
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                errors[field] = [message]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
