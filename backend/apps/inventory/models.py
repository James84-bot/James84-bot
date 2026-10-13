from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import OrgOwnedModel, UUIDModel


class MovementType(models.TextChoices):
    OPENING = "opening", "Opening stock"
    RECEIPT = "receipt", "Goods received"
    PURCHASE_RETURN = "purchase_return", "Returned to supplier"
    SALE = "sale", "Sold"
    SALE_RETURN = "sale_return", "Customer return"
    ADJUSTMENT = "adjustment", "Adjustment"
    TRANSFER_OUT = "transfer_out", "Sent to branch"
    TRANSFER_IN = "transfer_in", "Received from branch"


class StockBalance(UUIDModel):
    """Current quantity and average cost of one product at one branch.

    Maintained only by `inventory.services.post_movement`. Can be rebuilt from
    StockMovement rows with `manage.py reconcile_stock`.
    """

    organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("accounts.Branch", on_delete=models.PROTECT, related_name="stock_balances")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="stock_balances")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    average_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    reorder_level = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True,
        help_text="Overrides the product's reorder level at this branch.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["branch", "product"], name="uniq_balance_branch_product")]
        indexes = [models.Index(fields=["organization", "product"])]

    @property
    def value(self) -> Decimal:
        return (self.quantity * self.average_cost).quantize(Decimal("0.01"))


class StockMovement(UUIDModel):
    """One change to stock at a branch. Never edited or deleted; corrections
    are new movements that reference the one they reverse."""

    organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("accounts.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="Positive in, negative out.")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    value = models.DecimalField(max_digits=18, decimal_places=2, help_text="quantity × unit cost, signed.")
    balance_after = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=200, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    reference = models.CharField(max_length=40, blank=True, help_text="Document number, e.g. INV-000123.")
    reverses = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by")
    flagged = models.BooleanField(default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "branch", "product", "created_at"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Stock movements cannot be changed; post a correcting movement instead")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Stock movements cannot be deleted")


class AdjustmentReason(models.TextChoices):
    OPENING = "opening", "Opening stock"
    COUNT = "count", "Stock count correction"
    DAMAGED = "damaged", "Damaged"
    EXPIRED = "expired", "Expired"
    LOSS = "loss", "Lost or stolen"
    FOUND = "found", "Found"
    OTHER = "other", "Other"


class StockAdjustment(OrgOwnedModel):
    number = models.CharField(max_length=20)
    branch = models.ForeignKey("accounts.Branch", on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=20, choices=AdjustmentReason.choices)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="uniq_adjustment_number")]


class StockAdjustmentLine(UUIDModel):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="Positive adds stock, negative removes.")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="+")


class TransferStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    DISPATCHED = "dispatched", "In transit"
    RECEIVED = "received", "Received"
    CANCELLED = "cancelled", "Cancelled"


class StockTransfer(OrgOwnedModel):
    """Goods moved between branches. Stock leaves the sending branch on
    dispatch and arrives at the receiving branch when someone there confirms
    receipt, so goods on a lorry are visible as "in transit"."""

    number = models.CharField(max_length=20)
    from_branch = models.ForeignKey("accounts.Branch", on_delete=models.PROTECT, related_name="+")
    to_branch = models.ForeignKey("accounts.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=TransferStatus.choices, default=TransferStatus.DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_transfer_number"),
            models.CheckConstraint(condition=~models.Q(from_branch=models.F("to_branch")), name="transfer_branches_differ"),
        ]


class StockTransferLine(UUIDModel):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, help_text="Cost at the sending branch on dispatch."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["transfer", "product"], name="uniq_transfer_line_product"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="transfer_line_qty_positive"),
        ]
