from django.db.models import Q, Sum

from apps.core.mixins import AuditedCrudMixin, DeleteUnusedMixin
from apps.core.permissions import Perm
from apps.core.views import OrgScopedViewSet

from .models import Category, Product, Supplier, Unit
from .serializers import CategorySerializer, ProductSerializer, SupplierSerializer, UnitSerializer

MASTER_DATA_PERMS = {
    "list": Perm.VIEW,
    "retrieve": Perm.VIEW,
    "create": Perm.MANAGE_MASTER_DATA,
    "update": Perm.MANAGE_MASTER_DATA,
    "partial_update": Perm.MANAGE_MASTER_DATA,
    "destroy": Perm.MANAGE_MASTER_DATA,
}


def truthy(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.lower() in ("1", "true", "yes")


class CategoryViewSet(AuditedCrudMixin, DeleteUnusedMixin, OrgScopedViewSet):
    model = Category
    serializer_class = CategorySerializer
    pagination_class = None
    required_permissions = MASTER_DATA_PERMS
    audit_label = "category"


class UnitViewSet(AuditedCrudMixin, DeleteUnusedMixin, OrgScopedViewSet):
    model = Unit
    serializer_class = UnitSerializer
    pagination_class = None
    required_permissions = MASTER_DATA_PERMS
    audit_label = "unit"


class SupplierViewSet(AuditedCrudMixin, OrgScopedViewSet):
    model = Supplier
    serializer_class = SupplierSerializer
    required_permissions = MASTER_DATA_PERMS
    audit_label = "supplier"

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if q := p.get("search", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(contact_person__icontains=q) | Q(phone__icontains=q))
        if (active := truthy(p.get("active"))) is not None:
            qs = qs.filter(is_active=active)
        return qs


class ProductViewSet(AuditedCrudMixin, OrgScopedViewSet):
    model = Product
    serializer_class = ProductSerializer
    required_permissions = MASTER_DATA_PERMS
    audit_label = "product"

    def audit_name(self, obj):
        return f"{obj.sku} ({obj.name})"

    def get_queryset(self):
        qs = super().get_queryset().select_related("category", "unit")
        p = self.request.query_params
        branch = p.get("branch")
        stock_filter = Q(stock_balances__branch_id=branch) if branch else Q()
        qs = qs.annotate(quantity_on_hand=Sum("stock_balances__quantity", filter=stock_filter))
        if q := p.get("search", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode=q))
        if category := p.get("category"):
            qs = qs.filter(category_id=category)
        if (active := truthy(p.get("active"))) is not None:
            qs = qs.filter(is_active=active)
        return qs.order_by("name")
