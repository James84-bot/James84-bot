"""Stock ledger operations.

`post_movement` is the only code path that changes stock. Every caller
(adjustments, transfers, goods receipts, invoices, credit notes) goes through
it, so the locking, costing and negative-stock rules live in one place.

Concurrency: the StockBalance row for (branch, product) is locked with
SELECT ... FOR UPDATE for the duration of the caller's transaction. A second
request for the same product at the same branch waits, then sees the updated
quantity. Multi-line documents lock rows in a fixed order (by product ID) so
two documents touching the same products cannot deadlock each other.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError, ConflictError
from apps.core.models import DocumentSequence
from apps.core.money import ZERO, cost, money, qty

from .models import (
    AdjustmentReason,
    MovementType,
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockMovement,
    StockTransfer,
    TransferStatus,
)

INCOMING_NEEDS_COST = {MovementType.OPENING, MovementType.RECEIPT, MovementType.TRANSFER_IN, MovementType.SALE_RETURN}


def _fmt(q: Decimal) -> str:
    return f"{q.normalize():f}"


def validate_quantity(product, quantity: Decimal) -> Decimal:
    quantity = qty(quantity)
    if not product.unit.allow_fractions and quantity != quantity.to_integral_value():
        raise BusinessRuleError(
            f"{product.name} is counted in whole {product.unit.code}. Enter a whole number.",
            code="whole_units_only",
            product=str(product.id),
        )
    return quantity


def lock_balance(organization, branch, product) -> StockBalance:
    # Create the row if it does not exist without racing another request,
    # then lock it.
    StockBalance.objects.bulk_create(
        [StockBalance(organization=organization, branch=branch, product=product)], ignore_conflicts=True
    )
    return StockBalance.objects.select_for_update().get(branch=branch, product=product)


def post_movement(
    *,
    organization,
    branch,
    product,
    quantity: Decimal,
    movement_type: str,
    actor,
    unit_cost: Decimal | None = None,
    reason: str = "",
    source=None,
    source_type: str = "",
    source_id: str = "",
    reference: str = "",
    reverses: StockMovement | None = None,
) -> StockMovement:
    """Record one stock change and update the branch balance.

    `quantity` is signed: positive brings stock in, negative takes it out.
    Must run inside a transaction (the caller's), so that the movement, the
    balance and the source document commit together.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("post_movement must run inside a transaction")
    if product.organization_id != organization.id or branch.organization_id != organization.id:
        raise BusinessRuleError("Product or branch belongs to a different organisation.", code="wrong_organization")
    if not branch.is_active:
        raise BusinessRuleError(f"{branch.name} is closed and cannot record stock.", code="branch_inactive")

    quantity = validate_quantity(product, quantity)
    if quantity == ZERO:
        raise BusinessRuleError("Quantity cannot be zero.", code="zero_quantity")

    balance = lock_balance(organization, branch, product)
    old_qty, old_avg = balance.quantity, balance.average_cost
    new_qty = old_qty + quantity
    flagged = False

    if quantity > 0:
        if unit_cost is None:
            if movement_type in INCOMING_NEEDS_COST:
                raise BusinessRuleError("A unit cost is required for incoming stock.", code="cost_required")
            if old_avg == ZERO:
                raise BusinessRuleError(
                    f"{product.name} has no cost yet at {branch.name}. Enter the unit cost.", code="cost_required"
                )
            unit_cost = old_avg
        unit_cost = cost(unit_cost)
        if unit_cost < 0:
            raise BusinessRuleError("Unit cost cannot be negative.", code="negative_cost")
        if new_qty > 0:
            # Weighted average across what is physically on hand. If the
            # balance was negative, the units already sold are treated as
            # consumed, so the incoming cost becomes the new average.
            held_qty = old_qty if old_qty > 0 else ZERO
            new_avg = cost((held_qty * old_avg + quantity * unit_cost) / (held_qty + quantity))
        else:
            new_avg = old_avg
    else:
        unit_cost = cost(unit_cost) if unit_cost is not None else old_avg
        new_avg = old_avg
        if new_qty < 0:
            if not organization.allow_negative_stock:
                raise BusinessRuleError(
                    f"Not enough {product.name} at {branch.name}. "
                    f"Available: {_fmt(old_qty)} {product.unit.code}, requested: {_fmt(-quantity)} {product.unit.code}.",
                    code="insufficient_stock",
                    product=str(product.id),
                    branch=str(branch.id),
                    available=str(old_qty),
                    requested=str(-quantity),
                )
            flagged = True

    balance.quantity = new_qty
    balance.average_cost = new_avg
    balance.save(update_fields=["quantity", "average_cost", "updated_at"])

    movement = StockMovement.objects.create(
        organization=organization,
        branch=branch,
        product=product,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        value=money(quantity * unit_cost),
        balance_after=new_qty,
        reason=reason[:200],
        source_type=source._meta.label_lower if source is not None else source_type,
        source_id=str(source.pk) if source is not None else source_id,
        reference=reference,
        reverses=reverses,
        flagged=flagged,
        actor=actor,
    )
    if flagged:
        audit.record(
            organization=organization,
            actor=actor,
            action="stock.negative",
            entity=movement,
            summary=f"{product.name} at {branch.name} went below zero ({_fmt(new_qty)} {product.unit.code}) via {reference or movement_type}",
            changes={"quantity_before": old_qty, "quantity_after": new_qty},
            flagged=True,
        )
    return movement


def reverse_movement(movement: StockMovement, *, actor, reason: str) -> StockMovement:
    """Post the exact opposite of `movement` at its original cost."""
    if StockMovement.objects.filter(reverses=movement).exists():
        raise ConflictError("This movement has already been reversed.", code="already_reversed")
    return post_movement(
        organization=movement.organization,
        branch=movement.branch,
        product=movement.product,
        quantity=-movement.quantity,
        movement_type=movement.movement_type,
        actor=actor,
        unit_cost=movement.unit_cost,
        reason=reason,
        source_type=movement.source_type,
        source_id=movement.source_id,
        reference=movement.reference,
        reverses=movement,
    )


# --- Adjustments -------------------------------------------------------------


@dataclass
class AdjustmentLineInput:
    product: object
    quantity: Decimal
    unit_cost: Decimal | None = None


def _sorted_lines(lines):
    return sorted(lines, key=lambda line: str(line.product.id))


def _check_duplicates(lines):
    seen = set()
    for line in lines:
        if line.product.id in seen:
            raise BusinessRuleError(f"{line.product.name} appears twice. Combine the lines.", code="duplicate_line")
        seen.add(line.product.id)


@transaction.atomic
def create_adjustment(*, organization, branch, reason: str, notes: str, lines: list[AdjustmentLineInput], actor):
    if not lines:
        raise BusinessRuleError("Add at least one product.", code="no_lines")
    _check_duplicates(lines)
    if reason == AdjustmentReason.OPENING and any(line.quantity <= 0 for line in lines):
        raise BusinessRuleError("Opening stock quantities must be positive.", code="opening_negative")
    if reason == AdjustmentReason.OPENING and any(line.unit_cost is None for line in lines):
        raise BusinessRuleError("Enter a unit cost for every opening stock line.", code="cost_required")

    number = DocumentSequence.next_number(organization, "adjustment", "ADJ")
    adj = StockAdjustment.objects.create(
        organization=organization, number=number, branch=branch, reason=reason, notes=notes, created_by=actor
    )
    mtype = MovementType.OPENING if reason == AdjustmentReason.OPENING else MovementType.ADJUSTMENT
    label = AdjustmentReason(reason).label
    summary_lines = []
    for line in _sorted_lines(lines):
        mv = post_movement(
            organization=organization,
            branch=branch,
            product=line.product,
            quantity=line.quantity,
            movement_type=mtype,
            actor=actor,
            unit_cost=line.unit_cost,
            reason=label if not notes else f"{label}: {notes}",
            source=adj,
            reference=number,
        )
        StockAdjustmentLine.objects.create(
            adjustment=adj, product=line.product, quantity=mv.quantity, unit_cost=mv.unit_cost, movement=mv
        )
        summary_lines.append({"product": line.product.sku, "quantity": mv.quantity, "unit_cost": mv.unit_cost})

    audit.record(
        organization=organization,
        actor=actor,
        action="stock.adjusted",
        entity=adj,
        summary=f"{number} at {branch.name}: {label}, {len(lines)} line(s)",
        changes={"reason": reason, "lines": summary_lines},
    )
    return adj


# --- Transfers ---------------------------------------------------------------


def _lock_transfer(transfer: StockTransfer) -> StockTransfer:
    return StockTransfer.objects.select_for_update().select_related("from_branch", "to_branch").get(pk=transfer.pk)


@transaction.atomic
def create_transfer(*, organization, from_branch, to_branch, notes: str, lines: list[AdjustmentLineInput], actor):
    if from_branch.id == to_branch.id:
        raise BusinessRuleError("Choose two different branches.", code="same_branch")
    if not lines:
        raise BusinessRuleError("Add at least one product.", code="no_lines")
    _check_duplicates(lines)
    for line in lines:
        if line.quantity <= 0:
            raise BusinessRuleError("Transfer quantities must be more than zero.", code="non_positive_quantity")
        validate_quantity(line.product, line.quantity)
    number = DocumentSequence.next_number(organization, "transfer", "TRF")
    tr = StockTransfer.objects.create(
        organization=organization, number=number, from_branch=from_branch, to_branch=to_branch, notes=notes,
        created_by=actor,
    )
    tr.lines.bulk_create([tr.lines.model(transfer=tr, product=line.product, quantity=qty(line.quantity)) for line in lines])
    audit.record(
        organization=organization, actor=actor, action="transfer.created", entity=tr,
        summary=f"{number}: {from_branch.name} → {to_branch.name}, {len(lines)} line(s)",
    )
    return tr


@transaction.atomic
def dispatch_transfer(transfer: StockTransfer, *, actor) -> StockTransfer:
    tr = _lock_transfer(transfer)
    if tr.status != TransferStatus.DRAFT:
        raise ConflictError(f"{tr.number} is already {tr.get_status_display().lower()}.", code="invalid_status")
    lines = list(tr.lines.select_related("product__unit"))
    for line in _sorted_lines(lines):
        mv = post_movement(
            organization=tr.organization, branch=tr.from_branch, product=line.product, quantity=-line.quantity,
            movement_type=MovementType.TRANSFER_OUT, actor=actor, reason=f"Sent to {tr.to_branch.name}",
            source=tr, reference=tr.number,
        )
        line.unit_cost = mv.unit_cost
        line.save(update_fields=["unit_cost"])
    tr.status = TransferStatus.DISPATCHED
    tr.dispatched_by, tr.dispatched_at = actor, timezone.now()
    tr.save(update_fields=["status", "dispatched_by", "dispatched_at", "updated_at"])
    audit.record(
        organization=tr.organization, actor=actor, action="transfer.dispatched", entity=tr,
        summary=f"{tr.number} dispatched from {tr.from_branch.name}",
    )
    return tr


@transaction.atomic
def receive_transfer(transfer: StockTransfer, *, actor) -> StockTransfer:
    tr = _lock_transfer(transfer)
    if tr.status != TransferStatus.DISPATCHED:
        raise ConflictError(f"{tr.number} cannot be received while {tr.get_status_display().lower()}.", code="invalid_status")
    for line in _sorted_lines(list(tr.lines.select_related("product__unit"))):
        post_movement(
            organization=tr.organization, branch=tr.to_branch, product=line.product, quantity=line.quantity,
            movement_type=MovementType.TRANSFER_IN, actor=actor, unit_cost=line.unit_cost,
            reason=f"Received from {tr.from_branch.name}", source=tr, reference=tr.number,
        )
    tr.status = TransferStatus.RECEIVED
    tr.received_by, tr.received_at = actor, timezone.now()
    tr.save(update_fields=["status", "received_by", "received_at", "updated_at"])
    audit.record(
        organization=tr.organization, actor=actor, action="transfer.received", entity=tr,
        summary=f"{tr.number} received at {tr.to_branch.name}",
    )
    return tr


@transaction.atomic
def cancel_transfer(transfer: StockTransfer, *, actor, reason: str) -> StockTransfer:
    """Cancel a draft, or a dispatched transfer that never arrived. In the
    second case the goods go back to the sending branch at their dispatch cost."""
    tr = _lock_transfer(transfer)
    if tr.status not in (TransferStatus.DRAFT, TransferStatus.DISPATCHED):
        raise ConflictError(f"{tr.number} is {tr.get_status_display().lower()} and cannot be cancelled.", code="invalid_status")
    if not reason.strip():
        raise BusinessRuleError("Give a reason for cancelling.", code="reason_required")
    if tr.status == TransferStatus.DISPATCHED:
        outs = StockMovement.objects.filter(
            source_type="inventory.stocktransfer", source_id=str(tr.pk), movement_type=MovementType.TRANSFER_OUT,
            reverses__isnull=True,
        ).select_related("product__unit", "branch", "organization")
        for mv in sorted(outs, key=lambda m: str(m.product_id)):
            reverse_movement(mv, actor=actor, reason=f"Transfer cancelled: {reason}")
    tr.status = TransferStatus.CANCELLED
    tr.cancelled_by, tr.cancelled_at = actor, timezone.now()
    tr.save(update_fields=["status", "cancelled_by", "cancelled_at", "updated_at"])
    audit.record(
        organization=tr.organization, actor=actor, action="transfer.cancelled", entity=tr,
        summary=f"{tr.number} cancelled: {reason}",
    )
    return tr
