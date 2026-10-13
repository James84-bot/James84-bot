import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, password_validation, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.permissions import Perm, Role
from apps.core.views import OrgContextMixin, OrgScopedViewSet

from .models import Branch, Invitation, Membership, User
from .serializers import (
    AcceptInvitationSerializer,
    BranchSerializer,
    InvitationSerializer,
    LoginSerializer,
    MemberSerializer,
    MeSerializer,
    OrganizationSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)

log = logging.getLogger(__name__)


def client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


# --- Authentication -----------------------------------------------------------


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the CSRF cookie so the browser app can send X-CSRFToken."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].lower()
        user = authenticate(request, email=email, password=s.validated_data["password"])
        if user is None:
            log.info("Failed sign-in for %s from %s", email, client_ip(request))
            audit.record(
                organization=None, actor=None, action="auth.login_failed", summary=f"Failed sign-in for {email}",
                ip_address=client_ip(request),
            )
            return Response({"detail": "Email or password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        audit.record(
            organization=None, actor=user, action="auth.login", summary=f"{user.email} signed in",
            ip_address=client_ip(request),
        )
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = PasswordChangeSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        audit.record(organization=None, actor=request.user, action="auth.password_changed",
                     summary=f"{request.user.email} changed their password", ip_address=client_ip(request))
        return Response({"detail": "Password changed."})


class PasswordResetRequestView(APIView):
    """Always answers the same way so the form cannot be used to find out
    which email addresses have accounts."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        s = PasswordResetRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=s.validated_data["email"], is_active=True).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            send_mail(
                "Reset your JMH Ops password",
                f"Hello {user.full_name},\n\nUse this link to choose a new password. It works once and expires in 3 days.\n\n{link}\n\n"
                "If you did not ask for this, you can ignore this email.",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            audit.record(organization=None, actor=None, action="auth.password_reset_requested",
                         summary=f"Password reset requested for {user.email}", ip_address=client_ip(request))
        return Response({"detail": "If that email has an account, a reset link is on its way."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            pk = force_str(urlsafe_base64_decode(s.validated_data["uid"]))
            user = User.objects.get(pk=pk, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError, Exception):
            user = None
        if user is None or not default_token_generator.check_token(user, s.validated_data["token"]):
            return Response({"detail": "This reset link is invalid or has expired. Request a new one."},
                            status=status.HTTP_400_BAD_REQUEST)
        password_validation.validate_password(s.validated_data["new_password"], user)
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])
        audit.record(organization=None, actor=user, action="auth.password_reset",
                     summary=f"{user.email} reset their password", ip_address=client_ip(request))
        return Response({"detail": "Password updated. You can now sign in."})


class InvitationPreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        inv = Invitation.find_open(token)
        if inv is None:
            return Response({"detail": "This invitation is invalid, used or expired."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "organization": inv.organization.name,
            "email": inv.email,
            "role": inv.role,
            "has_account": User.objects.filter(email__iexact=inv.email).exists(),
        })


class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        s = AcceptInvitationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv = Invitation.find_open(s.validated_data["token"])
        if inv is None:
            return Response({"detail": "This invitation is invalid, used or expired."}, status=status.HTTP_400_BAD_REQUEST)
        inv = Invitation.objects.select_for_update().get(pk=inv.pk)
        if not inv.is_open:
            return Response({"detail": "This invitation has already been used."}, status=status.HTTP_409_CONFLICT)

        user = User.objects.filter(email__iexact=inv.email).first()
        if user is not None:
            # Existing account: they must be signed in as that account.
            if not request.user.is_authenticated or request.user.pk != user.pk:
                return Response({"detail": f"Sign in as {inv.email} to accept this invitation."},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            name, password = s.validated_data.get("full_name", "").strip(), s.validated_data.get("password", "")
            errors = {}
            if not name:
                errors["full_name"] = ["Enter your name."]
            if not password:
                errors["password"] = ["Choose a password."]
            if errors:
                raise ValidationError(errors)
            candidate = User(email=inv.email, full_name=name)
            password_validation.validate_password(password, candidate)
            user = User.objects.create_user(email=inv.email, password=password, full_name=name)

        membership, created = Membership.objects.get_or_create(
            user=user, organization=inv.organization, defaults={"role": inv.role, "branch": inv.branch}
        )
        if not created:
            membership.role, membership.branch, membership.is_active = inv.role, inv.branch, True
            membership.save(update_fields=["role", "branch", "is_active", "updated_at"])
        inv.accepted_at = timezone.now()
        inv.save(update_fields=["accepted_at", "updated_at"])
        audit.record(organization=inv.organization, actor=user, action="member.joined", entity=membership,
                     summary=f"{user.email} joined as {membership.get_role_display()}", ip_address=client_ip(request))
        if not request.user.is_authenticated:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


# --- Organisation administration ---------------------------------------------


class OrganizationView(OrgContextMixin, APIView):
    required_permissions = {"get": Perm.VIEW, "patch": Perm.MANAGE_ORG}

    def get(self, request):
        return Response(OrganizationSerializer(self.organization).data)

    @transaction.atomic
    def patch(self, request):
        org = self.organization
        s = OrganizationSerializer(org, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        changes = audit.diff(org, list(s.validated_data.keys()), s.validated_data)
        s.save()
        if changes:
            audit.record(organization=org, actor=request.user, action="organization.updated", entity=org,
                         summary="Business settings changed: " + ", ".join(changes), changes=changes)
        return Response(s.data)


class BranchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, OrgScopedViewSet):
    model = Branch
    serializer_class = BranchSerializer
    pagination_class = None
    required_permissions = {
        "list": Perm.VIEW, "retrieve": Perm.VIEW,
        "create": Perm.MANAGE_USERS, "update": Perm.MANAGE_USERS, "partial_update": Perm.MANAGE_USERS,
    }

    def perform_create(self, serializer):
        branch = serializer.save(organization=self.organization)
        audit.record(organization=self.organization, actor=self.request.user, action="branch.created", entity=branch,
                     summary=f"Branch {branch.name} ({branch.code}) added")

    def perform_update(self, serializer):
        changes = audit.diff(serializer.instance, list(serializer.validated_data), serializer.validated_data)
        branch = serializer.save()
        if changes:
            audit.record(organization=self.organization, actor=self.request.user, action="branch.updated",
                         entity=branch, summary=f"Branch {branch.name} changed", changes=changes)


class MemberViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, OrgScopedViewSet):
    model = Membership
    serializer_class = MemberSerializer
    pagination_class = None
    required_permissions = {"list": Perm.MANAGE_USERS, "update": Perm.MANAGE_USERS, "partial_update": Perm.MANAGE_USERS}

    def get_queryset(self):
        return super().get_queryset().select_related("user", "branch").order_by("user__full_name")

    @transaction.atomic
    def perform_update(self, serializer):
        target = Membership.objects.select_for_update().get(pk=serializer.instance.pk)
        data = serializer.validated_data
        me = self.membership
        new_role = data.get("role", target.role)
        if target.pk == me.pk and ("role" in data and data["role"] != me.role or data.get("is_active") is False):
            raise PermissionDenied("You cannot change your own role or deactivate yourself.")
        touches_owner = target.role == Role.OWNER or new_role == Role.OWNER
        if touches_owner and me.role != Role.OWNER:
            raise PermissionDenied("Only an owner can change an owner, or make someone an owner.")
        losing_owner = target.role == Role.OWNER and (new_role != Role.OWNER or data.get("is_active") is False)
        if losing_owner:
            others = Membership.objects.filter(organization=self.organization, role=Role.OWNER, is_active=True).exclude(pk=target.pk)
            if not others.exists():
                raise BusinessRuleError("The business must keep at least one active owner.", code="last_owner")
        changes = audit.diff(target, list(data), data)
        member = serializer.save()
        if changes:
            audit.record(organization=self.organization, actor=self.request.user, action="member.updated",
                         entity=member, summary=f"Access changed for {member.user.email}", changes=changes)


class InvitationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, OrgScopedViewSet):
    model = Invitation
    serializer_class = InvitationSerializer
    pagination_class = None
    required_permissions = {"list": Perm.MANAGE_USERS, "create": Perm.MANAGE_USERS, "revoke": Perm.MANAGE_USERS}

    def get_queryset(self):
        return super().get_queryset().select_related("invited_by").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"]
        if Membership.objects.filter(organization=self.organization, user__email__iexact=email, is_active=True).exists():
            raise BusinessRuleError(f"{email} is already a member.", code="already_member")
        if s.validated_data["role"] == Role.ADMIN and self.membership.role != Role.OWNER:
            raise PermissionDenied("Only an owner can invite an administrator.")
        with transaction.atomic():
            Invitation.objects.filter(organization=self.organization, email=email, accepted_at__isnull=True,
                                      revoked_at__isnull=True).update(revoked_at=timezone.now())
            inv, token = Invitation.issue(
                organization=self.organization, email=email, role=s.validated_data["role"],
                branch=s.validated_data.get("branch"), invited_by=request.user,
            )
            audit.record(organization=self.organization, actor=request.user, action="member.invited", entity=inv,
                         summary=f"{email} invited as {inv.get_role_display()}")
        link = f"{settings.FRONTEND_URL}/accept-invitation?token={token}"
        send_mail(
            f"You have been invited to {self.organization.name} on JMH Ops",
            f"{request.user.full_name} has invited you to join {self.organization.name} as {inv.get_role_display()}.\n\n"
            f"Accept the invitation here (valid for 7 days):\n{link}\n",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
        return Response(self.get_serializer(inv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        inv = self.get_object()
        if not inv.is_open:
            raise BusinessRuleError("This invitation is no longer open.", code="not_open")
        inv.revoked_at = timezone.now()
        inv.save(update_fields=["revoked_at", "updated_at"])
        audit.record(organization=self.organization, actor=request.user, action="member.invitation_revoked",
                     entity=inv, summary=f"Invitation for {inv.email} withdrawn")
        return Response(self.get_serializer(inv).data)
