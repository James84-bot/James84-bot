from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import OrgOwnedModel


class Category(OrgOwnedModel):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [models.UniqueConstraint("organization", Lower("name"), name="uniq_category_name_per_org")]

    def __str__(self) -> str:
        return self.name


class Unit(OrgOwnedModel):
    """Unit of measure, e.g. "bag" (50 kg cement), "pc", "m", "kg", "ltr"."""

    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)
    allow_fractions = models.BooleanField(
        default=False, help_text="Allow quantities like 2.5. Leave off for items sold whole (bags, pieces)."
    )

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint("organization", Lower("code"), name="uniq_unit_code_per_org")]

    def __str__(self) -> str:
        return self.code


class Product(OrgOwnedModel):
    sku = models.CharField("SKU", max_length=40)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=50, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products")
    selling_price = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(0)],
        help_text="Default price per unit, excluding VAT, in the organisation's base currency.",
    )
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="Leave empty to use the organisation default. Use 0 for zero-rated or exempt items.",
    )
    reorder_level = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0"), validators=[MinValueValidator(0)],
        help_text="Warn when stock at a branch falls to this level or below. Branches can override it.",
    )
    preferred_supplier = models.ForeignKey(
        "catalog.Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint("organization", Lower("sku"), name="uniq_product_sku_per_org")]
        indexes = [models.Index(fields=["organization", "name"])]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"

    def effective_vat_rate(self) -> Decimal:
        return self.vat_rate if self.vat_rate is not None else self.organization.default_vat_rate


class Supplier(OrgOwnedModel):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    address = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="KES")
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint("organization", Lower("name"), name="uniq_supplier_name_per_org")]

    def __str__(self) -> str:
        return self.name
