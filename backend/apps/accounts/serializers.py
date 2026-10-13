from django.contrib.auth import password_validation
from rest_framework import serializers

from apps.core.permissions import ROLE_PERMISSIONS, Role

from .models import ROLE_CHOICES, Branch, Invitation, Membership, Organization, User


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id", "name", "legal_name", "kra_pin", "phone", "email", "address", "base_currency", "timezone",
            "default_vat_rate", "default_payment_terms_days", "allow_negative_stock",
            "over_receipt_tolerance_percent", "manager_approval_limit", "require_separate_approver",
        ]
        read_only_fields = ["id"]

    def validate_base_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a three-letter currency code, e.g. KES.")
        if self.instance and value != self.instance.base_currency:
            raise serializers.ValidationError("The base currency cannot change once records exist.")
        return value


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "code", "address", "is_active"]
        read_only_fields = ["id"]

    def validate_code(self, value):
        value = value.upper().strip()
        org = self.context["organization"]
        qs = Branch.objects.filter(organization=org, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Another branch already uses this code.")
        return value


class MembershipBriefSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    branch = BranchSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["organization", "role", "branch", "permissions"]

    def get_organization(self, m):
        return {"id": str(m.organization_id), "name": m.organization.name, "base_currency": m.organization.base_currency,
                "timezone": m.organization.timezone}

    def get_permissions(self, m):
        return sorted(p.value for p in ROLE_PERMISSIONS[Role(m.role)])


class MeSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "memberships"]
        read_only_fields = ["id", "email"]

    def get_memberships(self, user):
        qs = user.memberships.filter(is_active=True).select_related("organization", "branch")
        return MembershipBriefSerializer(qs, many=True).data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "This is not your current password."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        source="branch", queryset=Branch.objects.none(), allow_null=True, required=False
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "full_name", "role", "branch_id", "branch_name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("organization")
        if org is not None:
            self.fields["branch_id"].queryset = Branch.objects.filter(organization=org, is_active=True)


class InvitationSerializer(serializers.ModelSerializer):
    branch_id = serializers.PrimaryKeyRelatedField(
        source="branch", queryset=Branch.objects.none(), allow_null=True, required=False
    )
    invited_by_name = serializers.CharField(source="invited_by.full_name", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "branch_id", "invited_by_name", "expires_at", "accepted_at", "status", "created_at"]
        read_only_fields = ["id", "expires_at", "accepted_at", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("organization")
        if org is not None:
            self.fields["branch_id"].queryset = Branch.objects.filter(organization=org, is_active=True)

    def get_status(self, inv):
        if inv.accepted_at:
            return "accepted"
        if inv.revoked_at:
            return "revoked"
        return "pending" if inv.is_open else "expired"

    def validate_email(self, value):
        return value.lower()

    def validate_role(self, value):
        if value == Role.OWNER:
            raise serializers.ValidationError("Owners cannot be invited. Transfer ownership from settings instead.")
        return value


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    full_name = serializers.CharField(max_length=150, required=False)
    password = serializers.CharField(trim_whitespace=False, required=False)


ROLE_CHOICES_PUBLIC = ROLE_CHOICES
