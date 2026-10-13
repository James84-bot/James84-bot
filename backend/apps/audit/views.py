from django.db.models import Q
from rest_framework import mixins

from apps.core.dates import filter_created_between
from apps.core.permissions import Perm
from apps.core.views import OrgScopedViewSet

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    """Read-only. Sign-in events have no organisation; they are included for
    members of this organisation so owners can see account activity."""

    model = AuditEvent
    serializer_class = AuditEventSerializer
    required_permissions = {"list": Perm.VIEW_AUDIT, "retrieve": Perm.VIEW_AUDIT}

    def get_queryset(self):
        org = self.organization
        member_ids = org.memberships.values("user_id")
        qs = AuditEvent.objects.filter(
            Q(organization=org) | Q(organization__isnull=True, actor_id__in=member_ids)
        ).select_related("actor")
        p = self.request.query_params
        if act := p.get("action", "").strip():
            qs = qs.filter(action__startswith=act)
        if entity := p.get("entity_id", "").strip():
            qs = qs.filter(entity_id=entity)
        if actor := p.get("actor"):
            qs = qs.filter(actor_id=actor)
        if p.get("flagged") in ("1", "true"):
            qs = qs.filter(flagged=True)
        if q := p.get("search", "").strip():
            qs = qs.filter(summary__icontains=q)
        return filter_created_between(qs, org, p).order_by("-created_at")
