from django.db.models import BooleanField, Case, DecimalField, ExpressionWrapper, F, Q, Value, When
from django.db.models.functions import Coalesce
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.dates import filter_created_between
from apps.core.permissions import Perm
from apps.core.views import OrgScopedViewSet

from . import services
from .models import MovementType, StockAdjustment, StockBalance, StockMovement, StockTransfer
from .serializers import (
    AdjustmentCreateSerializer,
    AdjustmentSerializer,
    ReasonSerializer,
    StockBalanceSerializer,
    StockMovementSerializer,
    TransferCreateSerializer,
    TransferSerializer,
)


class BranchAccessMixin:
    def check_branch(self, branch):
        if not self.membership.can_use_branch(branch):
            raise PermissionDenied(f"Your account is limited to {self.membership.branch.name}.")


def with_reorder_info(qs):
    level = Coalesce(F("reorder_level"), F("product__reorder_level"), output_field=DecimalField(max_digits=14, decimal_places=3))
    return qs.annotate(effective_reorder_level=level).annotate(
        is_low=Case(
            When(Q(effective_reorder_level__gt=0) & Q(quantity__lte=F("effective_reorder_level")), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        stock_value=ExpressionWrapper(F("quantity") * F("average_cost"), output_field=DecimalField(max_digits=32, decimal_places=7)),
    )


class StockBalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, OrgScopedViewSet):
    """Stock on hand per branch. Only the reorder level can be edited here;
    quantities change only through documents."""

    model = StockBalance
    serializer_class = StockBalanceSerializer
    required_permissions = {
        "list": Perm.VIEW, "retrieve": Perm.VIEW,
        "update": Perm.MANAGE_MASTER_DATA, "partial_update": Perm.MANAGE_MASTER_DATA,
    }

    def get_queryset(self):
        qs = with_reorder_info(super().get_queryset().select_related("product__unit", "branch"))
        p = self.request.query_params
        if branch := p.get("branch"):
            qs = qs.filter(branch_id=branch)
        if product := p.get("product"):
            qs = qs.filter(product_id=product)
        if q := p.get("search", "").strip():
            qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q))
        if p.get("low") in ("1", "true"):
            qs = qs.filter(is_low=True, product__is_active=True)
        if p.get("in_stock") in ("1", "true"):
            qs = qs.exclude(quantity=0)
        return qs.order_by("product__name", "branch__name")

    def perform_update(self, serializer):
        changes = audit.diff(serializer.instance, ["reorder_level"], serializer.validated_data)
        bal = serializer.save()
        if changes:
            audit.record(organization=self.organization, actor=self.request.user, action="stock.reorder_level_changed",
                         entity=bal, summary=f"Reorder level for {bal.product.sku} at {bal.branch.name} changed",
                         changes=changes)

    def get_serializer(self, *args, **kwargs):
        # Only reorder_level is writable.
        if "data" in kwargs:
            kwargs["data"] = {k: v for k, v in kwargs["data"].items() if k == "reorder_level"}
            kwargs["partial"] = True
        return super().get_serializer(*args, **kwargs)


class StockMovementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    model = StockMovement
    serializer_class = StockMovementSerializer
    required_permissions = {"list": Perm.VIEW, "retrieve": Perm.VIEW}

    def get_queryset(self):
        qs = super().get_queryset().select_related("product__unit", "branch", "actor")
        p = self.request.query_params
        if branch := p.get("branch"):
            qs = qs.filter(branch_id=branch)
        if product := p.get("product"):
            qs = qs.filter(product_id=product)
        if mtype := p.get("type"):
            qs = qs.filter(movement_type__in=[t for t in mtype.split(",") if t in MovementType.values])
        if ref := p.get("reference", "").strip():
            qs = qs.filter(reference__iexact=ref)
        if p.get("flagged") in ("1", "true"):
            qs = qs.filter(flagged=True)
        return filter_created_between(qs, self.organization, p).order_by("-created_at")


class AdjustmentViewSet(BranchAccessMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    model = StockAdjustment
    serializer_class = AdjustmentSerializer
    required_permissions = {"list": Perm.VIEW, "retrieve": Perm.VIEW, "create": Perm.ADJUST_STOCK}

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "created_by").prefetch_related("lines__product__unit")
        p = self.request.query_params
        if branch := p.get("branch"):
            qs = qs.filter(branch_id=branch)
        return filter_created_between(qs, self.organization, p)

    def create(self, request):
        s = AdjustmentCreateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        self.check_branch(d["branch_id"])
        adj = services.create_adjustment(
            organization=self.organization, branch=d["branch_id"], reason=d["reason"], notes=d["notes"],
            lines=[services.AdjustmentLineInput(product=line["product_id"], quantity=line["quantity"],
                                                unit_cost=line.get("unit_cost")) for line in d["lines"]],
            actor=request.user,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=adj.pk)).data, status=status.HTTP_201_CREATED)


class TransferViewSet(BranchAccessMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    model = StockTransfer
    serializer_class = TransferSerializer
    required_permissions = {
        "list": Perm.VIEW, "retrieve": Perm.VIEW, "create": Perm.RECORD_STOCK,
        "send": Perm.RECORD_STOCK, "receive": Perm.RECORD_STOCK, "cancel": Perm.ADJUST_STOCK,
    }

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "from_branch", "to_branch", "created_by", "dispatched_by", "received_by"
        ).prefetch_related("lines__product__unit")
        p = self.request.query_params
        if st := p.get("status"):
            qs = qs.filter(status=st)
        if branch := p.get("branch"):
            qs = qs.filter(Q(from_branch_id=branch) | Q(to_branch_id=branch))
        return filter_created_between(qs, self.organization, p)

    def _respond(self, tr, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=tr.pk)).data, status=code)

    def create(self, request):
        s = TransferCreateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        self.check_branch(d["from_branch_id"])
        tr = services.create_transfer(
            organization=self.organization, from_branch=d["from_branch_id"], to_branch=d["to_branch_id"],
            notes=d["notes"],
            lines=[services.AdjustmentLineInput(product=line["product_id"], quantity=line["quantity"]) for line in d["lines"]],
            actor=request.user,
        )
        return self._respond(tr, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="dispatch")
    def send(self, request, pk=None):
        tr = self.get_object()
        self.check_branch(tr.from_branch)
        return self._respond(services.dispatch_transfer(tr, actor=request.user))

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        tr = self.get_object()
        self.check_branch(tr.to_branch)
        return self._respond(services.receive_transfer(tr, actor=request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tr = self.get_object()
        return self._respond(services.cancel_transfer(tr, actor=request.user, reason=s.validated_data["reason"]))
