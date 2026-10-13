"""Base views that enforce organisation scoping and role permissions."""

import uuid

from django.db import connection
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Membership

from .permissions import HasOrgPermission, Perm, role_has

ORG_HEADER = "HTTP_X_ORGANIZATION"


def resolve_membership(request) -> Membership:
    """Find the caller's active membership for the organisation named in the
    X-Organization header, or their only membership if the header is absent."""
    memberships = Membership.objects.filter(
        user=request.user, is_active=True, organization__isnull=False
    ).select_related("organization", "branch")
    org_id = request.META.get(ORG_HEADER)
    if org_id:
        try:
            uuid.UUID(org_id)
        except ValueError as exc:
            raise ValidationError({"organization": "Invalid organisation ID."}) from exc
        m = memberships.filter(organization_id=org_id).first()
        if m is None:
            raise PermissionDenied("You are not a member of this organisation.")
        return m
    ms = list(memberships[:2])
    if len(ms) == 1:
        return ms[0]
    if not ms:
        raise PermissionDenied("Your account is not linked to any organisation.")
    raise ValidationError({"organization": "Choose an organisation (X-Organization header)."})


class OrgContextMixin:
    """Attaches `request.organization` and `request.membership` before any
    permission check runs."""

    permission_classes = [IsAuthenticated, HasOrgPermission]
    required_permissions: dict[str, Perm] = {}

    def check_permissions(self, request):
        # Runs after authentication and before the role check.
        if request.user and request.user.is_authenticated and not hasattr(request, "membership"):
            request.membership = resolve_membership(request)
            request.organization = request.membership.organization
        super().check_permissions(request)

    @property
    def organization(self):
        return self.request.organization

    @property
    def membership(self):
        return self.request.membership

    def can(self, perm: Perm) -> bool:
        return role_has(self.membership.role, perm)

    def require(self, perm: Perm):
        if not self.can(perm):
            raise PermissionDenied("Your role does not allow this action.")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if hasattr(self.request, "organization"):
            ctx["organization"] = self.request.organization
            ctx["membership"] = self.request.membership
            ctx["can_view_costs"] = role_has(self.request.membership.role, Perm.VIEW_COSTS)
        return ctx

    def get_org_object(self, model, pk, **filters):
        """Fetch a record by ID within the current organisation, else 404."""
        try:
            return model.objects.get(pk=pk, organization=self.organization, **filters)
        except (model.DoesNotExist, ValueError, ValidationError) as exc:
            raise NotFound() from exc


class OrgScopedViewSet(OrgContextMixin, viewsets.GenericViewSet):
    model = None

    def get_queryset(self):
        return self.model.objects.filter(organization=self.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.organization)


def health(request):
    """Liveness and database readiness for load balancers and Docker."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - report any DB failure as unhealthy
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok}, status=200 if db_ok else 503)
