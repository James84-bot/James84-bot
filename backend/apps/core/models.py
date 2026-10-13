import uuid

from django.db import models, transaction


class UUIDModel(models.Model):
    """UUID primary keys so record IDs in URLs cannot be guessed or counted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrgOwnedModel(TimeStampedModel):
    """Base for every record that belongs to one organisation."""

    organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True


class DocumentSequence(models.Model):
    """Per-organisation counters for document numbers (PO-000001, INV-000001).

    The row is locked while a number is allocated, so two parallel requests
    never receive the same number. If the surrounding transaction rolls back,
    the increment rolls back too, so committed numbers have no gaps.
    """

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    key = models.CharField(max_length=20)
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="uniq_sequence_per_org")]

    @classmethod
    def next_number(cls, organization, key: str, prefix: str, width: int = 6) -> str:
        if not transaction.get_connection().in_atomic_block:
            raise RuntimeError("Document numbers must be allocated inside a transaction")
        cls.objects.get_or_create(organization=organization, key=key)
        seq = cls.objects.select_for_update().get(organization=organization, key=key)
        value = seq.next_value
        seq.next_value = value + 1
        seq.save(update_fields=["next_value"])
        return f"{prefix}-{value:0{width}d}"
