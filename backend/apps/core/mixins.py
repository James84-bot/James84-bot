from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import mixins, status
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError


class AuditedCrudMixin(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       mixins.UpdateModelMixin):
    """List/create/update with an audit event for every create and change.

    `audit_label` names the record type in plain English; `audit_name(obj)`
    returns how the record is named in the summary. Deletion is deliberately
    not offered: records are deactivated so history stays intact.
    """

    audit_label = "record"
    audited_fields: list[str] | None = None

    def audit_name(self, obj) -> str:
        return str(obj)

    def _action_prefix(self) -> str:
        return self.model._meta.model_name

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save(organization=self.organization)
        audit.record(organization=self.organization, actor=self.request.user, action=f"{self._action_prefix()}.created",
                     entity=obj, summary=f"{self.audit_label.capitalize()} {self.audit_name(obj)} added",
                     changes={k: v for k, v in serializer.validated_data.items() if not hasattr(v, "pk")})

    @transaction.atomic
    def perform_update(self, serializer):
        fields = self.audited_fields or list(serializer.validated_data)
        changes = audit.diff(serializer.instance, fields, serializer.validated_data)
        obj = serializer.save()
        if changes:
            audit.record(organization=self.organization, actor=self.request.user,
                         action=f"{self._action_prefix()}.updated", entity=obj,
                         summary=f"{self.audit_label.capitalize()} {self.audit_name(obj)} changed: " + ", ".join(changes),
                         changes=changes)


class DeleteUnusedMixin(mixins.DestroyModelMixin):
    """Allow deleting lookup records (categories, units) only while nothing uses them."""

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        try:
            with transaction.atomic():
                name = str(obj)
                obj.delete()
                audit.record(organization=self.organization, actor=request.user,
                             action=f"{self.model._meta.model_name}.deleted",
                             summary=f"{self.audit_label.capitalize()} {name} deleted")
        except ProtectedError as exc:
            raise BusinessRuleError(f"This {self.audit_label} is in use and cannot be deleted.", code="in_use") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
