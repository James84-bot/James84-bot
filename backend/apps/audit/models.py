import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only record of an important action.

    Edits and deletes are refused here and, independently, by a database
    trigger (see migration 0002), so even direct SQL from the application
    role cannot rewrite history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)
    summary = models.CharField(max_length=300)
    changes = models.JSONField(default=dict, blank=True)
    flagged = models.BooleanField(default=False, help_text="Needs attention, e.g. stock taken below zero.")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit events cannot be changed")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events cannot be deleted")
