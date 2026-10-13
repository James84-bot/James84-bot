from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Branch
from apps.catalog.models import Product
from apps.core.serializers import OrgRelatedField

from .models import (
    AdjustmentReason,
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockMovement,
    StockTransfer,
    StockTransferLine,
)


class CostHidingMixin:
    """Removes cost and value fields for roles that may not see them
    (clerks see quantities only)."""

    cost_fields: tuple[str, ...] = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("can_view_costs", False):
            for f in self.cost_fields:
                data.pop(f, None)
        return data


class StockBalanceSerializer(CostHidingMixin, serializers.ModelSerializer):
    cost_fields = ("average_cost", "value")

    product_id = serializers.UUIDField(source="product.id", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    branch_id = serializers.UUIDField(source="branch.id", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    effective_reorder_level = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    is_low = serializers.BooleanField(read_only=True)
    value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = StockBalance
        fields = [
            "id", "product_id", "sku", "product_name", "unit_code", "branch_id", "branch_name", "quantity",
            "reorder_level", "effective_reorder_level", "is_low", "average_cost", "value", "updated_at",
        ]
        read_only_fields = ["id", "quantity", "average_cost", "updated_at"]


class StockMovementSerializer(CostHidingMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost", "value")

    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    movement_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    is_reversal = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id", "created_at", "branch_id", "branch_name", "product_id", "sku", "product_name", "unit_code",
            "movement_type", "movement_label", "quantity", "unit_cost", "value", "balance_after", "reason",
            "reference", "source_type", "source_id", "is_reversal", "flagged", "actor_name",
        ]

    def get_is_reversal(self, obj) -> bool:
        return obj.reverses_id is not None


class LineInputSerializer(serializers.Serializer):
    product_id = OrgRelatedField(model=Product, extra_filter={"is_active": True})
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True, min_value=Decimal("0")
    )


class AdjustmentCreateSerializer(serializers.Serializer):
    branch_id = OrgRelatedField(model=Branch, extra_filter={"is_active": True})
    reason = serializers.ChoiceField(choices=AdjustmentReason.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    lines = LineInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        if attrs["reason"] == AdjustmentReason.OTHER and not attrs.get("notes", "").strip():
            raise serializers.ValidationError({"notes": "Explain the adjustment when the reason is Other."})
        return attrs


class AdjustmentLineSerializer(CostHidingMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost",)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)

    class Meta:
        model = StockAdjustmentLine
        fields = ["id", "product_id", "sku", "product_name", "unit_code", "quantity", "unit_cost"]


class AdjustmentSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    lines = AdjustmentLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockAdjustment
        fields = ["id", "number", "branch_id", "branch_name", "reason", "reason_label", "notes", "created_by_name",
                  "created_at", "lines"]


class TransferLineSerializer(CostHidingMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost",)
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)

    class Meta:
        model = StockTransferLine
        fields = ["id", "product_id", "sku", "product_name", "unit_code", "quantity", "unit_cost"]


class TransferSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    dispatched_by_name = serializers.CharField(source="dispatched_by.full_name", read_only=True, default=None)
    received_by_name = serializers.CharField(source="received_by.full_name", read_only=True, default=None)
    lines = TransferLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id", "number", "from_branch_id", "from_branch_name", "to_branch_id", "to_branch_name", "status",
            "status_label", "notes", "created_by_name", "created_at", "dispatched_by_name", "dispatched_at",
            "received_by_name", "received_at", "cancelled_at", "lines",
        ]


class TransferCreateSerializer(serializers.Serializer):
    from_branch_id = OrgRelatedField(model=Branch, extra_filter={"is_active": True})
    to_branch_id = OrgRelatedField(model=Branch, extra_filter={"is_active": True})
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    lines = LineInputSerializer(many=True, allow_empty=False)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)
