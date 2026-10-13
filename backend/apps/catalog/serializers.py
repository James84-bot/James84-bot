from rest_framework import serializers

from apps.core.serializers import OrgRelatedField, UniqueInOrgMixin

from .models import Category, Product, Supplier, Unit


class CategorySerializer(UniqueInOrgMixin, serializers.ModelSerializer):
    unique_in_org = {"name": "A category with this name already exists."}

    class Meta:
        model = Category
        fields = ["id", "name"]


class UnitSerializer(UniqueInOrgMixin, serializers.ModelSerializer):
    unique_in_org = {"code": "A unit with this code already exists."}

    class Meta:
        model = Unit
        fields = ["id", "code", "name", "allow_fractions"]


class SupplierSerializer(UniqueInOrgMixin, serializers.ModelSerializer):
    unique_in_org = {"name": "A supplier with this name already exists."}

    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_person", "phone", "email", "kra_pin", "address", "currency",
                  "payment_terms_days", "is_active"]

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a three-letter currency code, e.g. KES or USD.")
        return value


class ProductSerializer(UniqueInOrgMixin, serializers.ModelSerializer):
    unique_in_org = {"sku": "Another product already uses this SKU."}

    category_id = OrgRelatedField(source="category", model=Category, allow_null=True, required=False)
    unit_id = OrgRelatedField(source="unit", model=Unit)
    preferred_supplier_id = OrgRelatedField(source="preferred_supplier", model=Supplier, allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    allow_fractions = serializers.BooleanField(source="unit.allow_fractions", read_only=True)
    quantity_on_hand = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, default=None)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description", "barcode", "category_id", "category_name", "unit_id", "unit_code",
            "allow_fractions", "selling_price", "vat_rate", "reorder_level", "preferred_supplier_id", "is_active",
            "quantity_on_hand", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Enter a SKU.")
        return value
