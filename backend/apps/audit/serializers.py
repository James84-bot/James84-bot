from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    actor_email = serializers.CharField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = ["id", "created_at", "action", "summary", "entity_type", "entity_id", "changes", "flagged",
                  "actor_name", "actor_email", "ip_address", "request_id"]
