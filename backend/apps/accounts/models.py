import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel
from apps.core.permissions import ROLE_LABELS, Role

ROLE_CHOICES = [(r.value, ROLE_LABELS[r]) for r in Role]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create_user(email, password, **extra)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can sign in to the Django admin site.")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci")]

    def __str__(self) -> str:
        return self.full_name or self.email


class Organization(TimeStampedModel):
    """A business using JMH Ops. Business rules that differ between companies
    are settings here rather than assumptions in code."""

    name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    base_currency = models.CharField(max_length=3, default="KES")
    timezone = models.CharField(max_length=50, default="Africa/Nairobi")
    default_vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("16.00"), validators=[MinValueValidator(0)]
    )
    default_payment_terms_days = models.PositiveSmallIntegerField(default=30)

    allow_negative_stock = models.BooleanField(
        default=False, help_text="If on, sales can take stock below zero. Every such sale is flagged in the audit log."
    )
    over_receipt_tolerance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
        help_text="How much more than ordered may be received on a purchase order line.",
    )
    manager_approval_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Largest purchase order (in base currency) a manager may approve. Empty means no limit.",
    )
    require_separate_approver = models.BooleanField(
        default=True, help_text="The person who created a purchase order cannot approve it."
    )

    def __str__(self) -> str:
        return self.name


class Branch(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="branches")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="uniq_branch_code_per_org")]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Membership(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="If set, this person can only record stock activity at this branch.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="uniq_membership")]

    def __str__(self) -> str:
        return f"{self.user} — {self.organization} ({self.role})"

    def can_use_branch(self, branch: Branch) -> bool:
        return self.branch_id is None or self.branch_id == branch.id


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Invitation(TimeStampedModel):
    """An emailed link that lets someone create their account and join an
    organisation with a given role. Only a hash of the token is stored."""

    VALID_FOR = timedelta(days=7)

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, **fields) -> tuple["Invitation", str]:
        token = secrets.token_urlsafe(32)
        inv = cls.objects.create(
            token_hash=_hash_token(token), expires_at=timezone.now() + cls.VALID_FOR, **fields
        )
        return inv, token

    @classmethod
    def find_open(cls, token: str) -> "Invitation | None":
        inv = cls.objects.filter(token_hash=_hash_token(token)).select_related("organization", "branch").first()
        if inv is None or not inv.is_open:
            return None
        return inv

    @property
    def is_open(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > timezone.now()
