import hashlib
import uuid
import secrets
from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


class TenantPlan(models.TextChoices):
    STARTER = 'STARTER', 'Starter Plan'
    PRO = 'PRO', 'Professional Plan'
    ENTERPRISE = 'ENTERPRISE', 'Enterprise Plan'


class PriceDisplayMode(models.TextChoices):
    CONTACT_SALES = 'CONTACT_SALES', 'Contact Sales'
    CUSTOM_QUOTE = 'CUSTOM_QUOTE', 'Custom Quote'
    AMOUNT = 'AMOUNT', 'Fixed Amount'


class PlanTier(models.Model):
    """
    Configurable subscription plan definition with enforceable limits and module entitlements.
    Supports Basic, Growth, Pro, Enterprise, and custom plans.
    """
    code = models.CharField(max_length=40, unique=True, help_text="Unique code, e.g. basic, growth, pro, enterprise")
    name = models.CharField(max_length=100)
    badge = models.CharField(max_length=50, blank=True, help_text="e.g. Popular, Best Value")
    description = models.TextField(blank=True)
    price_display_mode = models.CharField(
        max_length=20,
        choices=PriceDisplayMode.choices,
        default=PriceDisplayMode.CONTACT_SALES,
        help_text="Public pricing display mode. Defaults to Contact Sales."
    )
    currency = models.CharField(max_length=10, default='INR')
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_published = models.BooleanField(default=True, help_text="Visible on marketing pricing page")
    is_featured = models.BooleanField(default=False)
    ordering = models.PositiveIntegerField(default=0)

    # Enforceable Entitlements & Limits
    max_staff = models.PositiveIntegerField(default=2, help_text="Agent seats included (Owner and Admins count toward seats)")
    max_contacts = models.PositiveIntegerField(default=1000, help_text="Maximum customer contacts allowed")
    max_services = models.PositiveIntegerField(default=10, help_text="Maximum active services in catalog")
    max_documents = models.PositiveIntegerField(default=5, help_text="Maximum knowledge documents/FAQs")
    monthly_message_allowance = models.PositiveIntegerField(default=500, help_text="Included monthly delivery messages")
    ai_assistant_enabled = models.BooleanField(default=True)
    crm_enabled = models.BooleanField(default=True)
    enabled_modules = models.JSONField(default=list, blank=True, help_text="List of enabled module keys")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordering', 'name']
        verbose_name = "Plan Tier"
        verbose_name_plural = "Plan Tiers"

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def annual_savings_percent(self) -> int:
        if self.monthly_price and self.annual_price and self.monthly_price > 0:
            annual_cost_from_monthly = self.monthly_price * 12
            savings = annual_cost_from_monthly - self.annual_price
            if savings > 0:
                return int(round((savings / annual_cost_from_monthly) * 100))
        return 0


class Tenant(models.Model):
    """
    SaaS Tenant representing a distinct customer business on the platform.
    """
    name = models.CharField(max_length=150, unique=True, help_text="Business / organization name")
    slug = models.SlugField(max_length=160, unique=True, blank=True, help_text="URL slug / unique identifier")
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this tenant is active. Suspended tenants cannot process messages."
    )
    plan = models.CharField(
        max_length=30,
        choices=TenantPlan.choices,
        default=TenantPlan.STARTER,
        help_text="Assigned subscription plan"
    )
    max_services = models.PositiveIntegerField(default=25, help_text="Configured service limit")
    max_staff = models.PositiveIntegerField(default=10, help_text="Configured team member limit")
    
    logo = models.FileField(upload_to='tenant_logos/', null=True, blank=True, help_text="Uploaded client logo")
    logo_url = models.URLField(max_length=500, blank=True, null=True, help_text="Direct URL to client logo image")
    timezone = models.CharField(max_length=50, default='Asia/Kolkata', help_text="Client primary timezone")
    contact_email = models.EmailField(blank=True, help_text="Primary business contact email")
    requires_meta_setup = models.BooleanField(default=False)
    whatsapp_number = models.CharField(max_length=16, blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, help_text="Primary business contact phone")
    outbound_paused = models.BooleanField(default=False, help_text="Platform operator kill-switch pausing outbound WhatsApp sends")
    outbound_pause_reason = models.CharField(max_length=255, blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        constraints = [
            models.UniqueConstraint(fields=['whatsapp_number'], condition=~models.Q(whatsapp_number=''), name='tenant_unique_whatsapp_number'),
        ]

    def __str__(self):
        status = "Active" if self.is_active else "Suspended"
        return f"{self.name} [{status}]"

    @property
    def effective_logo_url(self) -> str:
        if self.logo:
            try:
                return self.logo.url
            except Exception:
                pass
        if (self.logo_url or '').startswith('s3://'):
            from .media_api import client_media_url
            return client_media_url(self)
        return self.logo_url or ''

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_subscription_active(self) -> bool:
        if not self.is_active:
            return False
        if hasattr(self, 'subscription'):
            return self.subscription.status == SubscriptionStatus.ACTIVE or self.subscription.is_in_grace
        return True

    @property
    def active_staff_count(self) -> int:
        return self.memberships.filter(is_active=True).count()

    def can_add_staff(self) -> bool:
        memberships_count = self.memberships.filter(is_active=True).count()
        pending_invites_count = self.invitations.filter(is_accepted=False, expires_at__gt=timezone.now()).count() if hasattr(self, 'invitations') else 0
        return (memberships_count + pending_invites_count) < self.effective_max_staff

    @property
    def effective_max_staff(self) -> int:
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            return self.subscription.effective_plan.max_staff
        return self.max_staff

    @property
    def effective_max_services(self) -> int:
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            return self.subscription.effective_plan.max_services
        return self.max_services

    @property
    def effective_max_contacts(self) -> int:
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            return self.subscription.effective_plan.max_contacts
        return 1000

    @property
    def effective_max_documents(self) -> int:
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            return self.subscription.effective_plan.max_documents
        return 10

    @property
    def effective_monthly_message_allowance(self) -> int:
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            return self.subscription.effective_plan.monthly_message_allowance
        return 1000

    @property
    def active_contacts_count(self) -> int:
        return self.customers.count()

    @property
    def active_documents_count(self) -> int:
        return self.documents.filter(is_active=True).count() if hasattr(self, 'documents') else 0

    def can_add_contact(self) -> bool:
        return self.active_contacts_count < self.effective_max_contacts

    def can_add_service(self) -> bool:
        return self.services.filter(is_active=True).count() < self.effective_max_services

    def can_add_document(self) -> bool:
        return self.active_documents_count < self.effective_max_documents

    def get_current_monthly_usage(self):
        now = timezone.now()
        usage, _ = TenantMonthlyUsage.objects.get_or_create(
            tenant=self,
            year=now.year,
            month=now.month
        )
        return usage

    def can_send_monthly_message(self) -> bool:
        if not self.is_subscription_active:
            return False
        usage = self.get_current_monthly_usage()
        current_allocated = usage.outbound_messages_sent + usage.outbound_messages_reserved
        return current_allocated < self.effective_monthly_message_allowance

    def reserve_monthly_message_slot(self) -> bool:
        """
        Atomically reserves a monthly outbound message slot before slow provider calls.
        Guards against concurrent dispatch race conditions and over-quota sends.
        """
        if not self.is_subscription_active:
            return False

        with transaction.atomic():
            now = timezone.now()
            usage, _ = TenantMonthlyUsage.objects.select_for_update().get_or_create(
                tenant=self,
                year=now.year,
                month=now.month
            )
            current_allocated = usage.outbound_messages_sent + usage.outbound_messages_reserved
            if current_allocated >= self.effective_monthly_message_allowance:
                return False

            usage.outbound_messages_reserved += 1
            usage.outbound_messages_attempted += 1
            usage.save(update_fields=['outbound_messages_reserved', 'outbound_messages_attempted', 'updated_at'])
            return True

    def finalize_monthly_message_reservation(self, succeeded: bool = True):
        """
        Finalizes an existing reservation after provider dispatch completes.
        If succeeded: converts reservation to committed sent count.
        If failed: releases reservation without charging sent count.
        """
        with transaction.atomic():
            now = timezone.now()
            usage = TenantMonthlyUsage.objects.select_for_update().filter(
                tenant=self,
                year=now.year,
                month=now.month
            ).first()
            if not usage:
                return

            if usage.outbound_messages_reserved > 0:
                usage.outbound_messages_reserved -= 1
            if succeeded:
                usage.outbound_messages_sent += 1
            usage.save(update_fields=['outbound_messages_reserved', 'outbound_messages_sent', 'updated_at'])

    def release_monthly_message_reservation(self):
        self.finalize_monthly_message_reservation(succeeded=False)

    def increment_monthly_message_usage(self, sent: bool = True):
        now = timezone.now()
        with transaction.atomic():
            usage, _ = TenantMonthlyUsage.objects.select_for_update().get_or_create(
                tenant=self,
                year=now.year,
                month=now.month
            )
            usage.outbound_messages_attempted += 1
            if sent:
                usage.outbound_messages_sent += 1
            usage.save(update_fields=['outbound_messages_attempted', 'outbound_messages_sent', 'updated_at'])
            return usage

    def get_feature_override(self, feature_key: str) -> str:
        override = self.feature_overrides.filter(feature_key=feature_key).first()
        if override:
            return override.override
        return 'INHERIT'

    def is_module_enabled(self, module_key: str) -> bool:
        # Check explicit override first
        override = self.get_feature_override(module_key)
        if override == 'DENY':
            return False
        if override == 'ALLOW':
            return True
        if hasattr(self, 'subscription') and self.subscription.effective_plan:
            plan_modules = self.subscription.effective_plan.enabled_modules
            if plan_modules:
                return module_key in plan_modules
        return True


class SubscriptionStatus(models.TextChoices):
    PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Platform Approval'
    ACTIVE = 'ACTIVE', 'Active'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    EXPIRED = 'EXPIRED', 'Expired'


class TenantSubscription(models.Model):
    """
    Subscription state separate from payment gateways.
    Manages requested tier, platform-approved tier, activation state, and validity dates.
    """
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='subscription')
    requested_plan = models.ForeignKey(
        PlanTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_subscriptions'
    )
    effective_plan = models.ForeignKey(
        PlanTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='effective_subscriptions'
    )
    status = models.CharField(
        max_length=30,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING_APPROVAL
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_subscriptions'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    grace_until = models.DateField(null=True, blank=True, help_text="Optional grace-period extension date")
    grace_notes = models.TextField(blank=True, default='')
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_in_grace(self) -> bool:
        return bool(
            self.grace_until
            and self.grace_until >= timezone.localdate()
            and self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED)
        )

    class Meta:
        verbose_name = "Tenant Subscription"
        verbose_name_plural = "Tenant Subscriptions"

    def __str__(self):
        plan_name = self.effective_plan.name if self.effective_plan else "Unassigned"
        return f"{self.tenant.name} -> {plan_name} [{self.get_status_display()}]"

    def approve(self, approver_user, plan=None):
        self.status = SubscriptionStatus.ACTIVE
        self.approved_by = approver_user
        self.approved_at = timezone.now()
        if plan:
            self.effective_plan = plan
        elif not self.effective_plan and self.requested_plan:
            self.effective_plan = self.requested_plan
        self.save()
        if self.effective_plan:
            self.tenant.max_staff = self.effective_plan.max_staff
            self.tenant.max_services = self.effective_plan.max_services
            self.tenant.save(update_fields=['max_staff', 'max_services'])


class TenantRole(models.TextChoices):
    OWNER = 'OWNER', 'Tenant Owner'
    ADMIN = 'ADMIN', 'Tenant Administrator'
    STAFF = 'STAFF', 'Tenant Staff'


MembershipRole = TenantRole  # Alias for compatibility


class TenantMembership(models.Model):
    """
    Associates a User with a Tenant under an explicit role.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tenant_memberships')
    role = models.CharField(
        max_length=20,
        choices=TenantRole.choices,
        default=TenantRole.STAFF,
        help_text="Role and permission level within this tenant"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this membership is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant Membership"
        verbose_name_plural = "Tenant Memberships"
        unique_together = ('tenant', 'user')
        ordering = ['tenant', 'role', 'user']

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()}) @ {self.tenant.name}"

    @property
    def is_owner_or_admin(self) -> bool:
        return self.role in (TenantRole.OWNER, TenantRole.ADMIN)


class TenantInvitation(models.Model):
    """
    Single-use, expiring invitation to join a tenant workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField(help_text="Email of the invited user")
    role = models.CharField(
        max_length=20,
        choices=TenantRole.choices,
        default=TenantRole.STAFF
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_invitations'
    )
    expires_at = models.DateTimeField(help_text="Invitation expiry timestamp")
    is_accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tenant Invitation"
        verbose_name_plural = "Tenant Invitations"

    def __str__(self):
        return f"Invite for {self.email} to {self.tenant.name} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        return not self.is_accepted and self.expires_at > timezone.now()

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @classmethod
    def create_invitation(cls, tenant, email, role=TenantRole.STAFF, invited_by=None, valid_days=7):
        expires_at = timezone.now() + timezone.timedelta(days=valid_days)
        return cls.objects.create(
            tenant=tenant,
            email=email,
            role=role,
            invited_by=invited_by,
            expires_at=expires_at
        )

    def accept(self, user):
        if self.is_accepted:
            raise ValueError("Invitation has already been accepted.")
        if self.is_expired:
            raise ValueError("Invitation has expired.")
        
        membership, created = TenantMembership.objects.get_or_create(
            tenant=self.tenant,
            user=user,
            defaults={'role': self.role, 'is_active': True}
        )
        if not created:
            membership.role = self.role
            membership.is_active = True
            membership.save(update_fields=['role', 'is_active', 'updated_at'])
        
        self.is_accepted = True
        self.accepted_at = timezone.now()
        self.save(update_fields=['is_accepted', 'accepted_at'])
        return membership


class StaffRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Super Admin Review'
    APPROVED = 'APPROVED', 'Approved & Provisioned'
    REJECTED = 'REJECTED', 'Rejected'


class StaffAccessRequest(models.Model):
    """
    Non-account-creating request submitted by a Client Administrator to Super Admin
    requesting a new team member / salesperson for their client workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='staff_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_staff_requests')
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=TenantRole.choices,
        default=TenantRole.STAFF
    )
    notes = models.TextField(blank=True, help_text="Reason or details for the staff request")
    status = models.CharField(
        max_length=20,
        choices=StaffRequestStatus.choices,
        default=StaffRequestStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_staff_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Staff Access Request"
        verbose_name_plural = "Staff Access Requests"

    def __str__(self):
        return f"Staff Request: {self.full_name} ({self.email}) for {self.tenant.name} [{self.get_status_display()}]"


class AccountActivationToken(models.Model):
    """
    Secure single-use token allowing a pre-provisioned identity to set their password.
    Stores SHA-256 digest only; plaintext token exists solely in transient creation memory
    and encrypted outbox payloads.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activation_tokens')
    purpose = models.CharField(max_length=32, default='ACCOUNT_ACTIVATION')
    legacy_token = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    token_digest = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Account Activation Token"
        verbose_name_plural = "Account Activation Tokens"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()

    @property
    def token(self):
        return getattr(self, '_raw_token', None) or self.legacy_token

    @classmethod
    def create_for_user(cls, user, valid_hours=48):
        # Invalidate any prior unused activation tokens for this user
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        raw_token = secrets.token_urlsafe(32)
        obj = cls.objects.create(
            user=user,
            purpose='ACCOUNT_ACTIVATION',
            legacy_token=None,
            token_digest=cls.hash_token(raw_token),
            expires_at=timezone.now() + timezone.timedelta(hours=valid_hours)
        )
        obj._raw_token = raw_token
        return obj

    @classmethod
    def lookup_by_raw(cls, raw_token: str):
        if not raw_token:
            return None
        digest = cls.hash_token(raw_token)
        return cls.objects.filter(
            models.Q(token_digest=digest) | models.Q(legacy_token=raw_token),
            purpose='ACCOUNT_ACTIVATION'
        ).select_related('user').first()

    @property
    def is_valid(self) -> bool:
        return not self.is_used and self.expires_at > timezone.now()


class OnboardingSource(models.TextChoices):
    SELF_REGISTRATION = 'SELF_REGISTRATION', 'Self Registration / Request Access'
    SUPERADMIN_INVITE = 'SUPERADMIN_INVITE', 'Super Admin Created & Invited'


class OnboardingApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Platform Approval'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class OnboardingRegistrationStatus(models.TextChoices):
    SUBMITTED = 'SUBMITTED', 'Submitted (Awaiting Email Verification)'
    EMAIL_VERIFIED = 'EMAIL_VERIFIED', 'Email Verified'
    APPROVED = 'APPROVED', 'Approved by Platform'
    REJECTED = 'REJECTED', 'Rejected by Platform'
    ACTIVE = 'ACTIVE', 'Password Set & Active'
    CANCELLED = 'CANCELLED', 'Cancelled'


class ClientOnboarding(models.Model):
    """
    Shared onboarding record unifying public registration and Super Admin client invitations.
    Tracks registration, email verification, platform approval, plan assignment, and password setup independently.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=30, choices=OnboardingSource.choices, default=OnboardingSource.SELF_REGISTRATION)
    business_name = models.CharField(max_length=150)
    owner_full_name = models.CharField(max_length=150)
    owner_email = models.EmailField(max_length=254, db_index=True)
    desired_username = models.CharField(max_length=150)
    whatsapp_number = models.CharField(max_length=20, blank=True, default='')
    requested_plan = models.ForeignKey(
        PlanTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_requests'
    )
    assigned_plan = models.ForeignKey(
        PlanTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_assignments'
    )
    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_document = models.ForeignKey(
        'LegalDocument',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_acceptances'
    )
    marketing_consent = models.BooleanField(default=False)
    marketing_consent_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    registration_status = models.CharField(
        max_length=30,
        choices=OnboardingRegistrationStatus.choices,
        default=OnboardingRegistrationStatus.SUBMITTED
    )
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=OnboardingApprovalStatus.choices,
        default=OnboardingApprovalStatus.PENDING
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_onboardings'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True, default='')
    password_set = models.BooleanField(default=False)
    password_set_at = models.DateTimeField(null=True, blank=True)

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_record'
    )
    owner_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_records'
    )
    demo_request = models.OneToOneField(
        'DemoRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_record'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Client Onboarding"
        verbose_name_plural = "Client Onboardings"

    def __str__(self):
        return f"{self.business_name} ({self.owner_email}) [{self.approval_status}]"


class VerificationPurpose(models.TextChoices):
    EMAIL_VERIFY = 'EMAIL_VERIFY', 'Owner / Registration Email Verification'
    RECOVERY_EMAIL_VERIFY = 'RECOVERY_EMAIL_VERIFY', 'Recovery Email Verification'


class EmailVerificationToken(models.Model):
    """
    Expiring (default 30 min), single-use, purpose-bound verification token.
    Stores SHA-256 digest only; plaintext token is never saved to the database.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='verification_tokens')
    onboarding = models.ForeignKey(ClientOnboarding, on_delete=models.CASCADE, null=True, blank=True, related_name='verification_tokens')
    purpose = models.CharField(max_length=32, choices=VerificationPurpose.choices, default=VerificationPurpose.EMAIL_VERIFY)
    intended_email = models.EmailField(max_length=254, blank=True, default='')
    legacy_token = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    token_digest = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    invalidation_reason = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()

    @property
    def token(self):
        return getattr(self, '_raw_token', None) or self.legacy_token

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=30)
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.invalidation_reason and self.expires_at > timezone.now()

    @classmethod
    def issue_token(cls, *, onboarding=None, user=None, intended_email='', purpose=VerificationPurpose.EMAIL_VERIFY, minutes=30):
        qs = cls.objects.filter(is_used=False, purpose=purpose)
        if onboarding is not None:
            qs = qs.filter(onboarding=onboarding)
        elif user is not None:
            qs = qs.filter(user=user)
        qs.update(is_used=True, invalidation_reason='SUPERSEDED')

        raw_token = secrets.token_urlsafe(32)
        obj = cls.objects.create(
            onboarding=onboarding,
            user=user,
            purpose=purpose,
            intended_email=(intended_email or (user.email if user else '') or '').strip(),
            legacy_token=None,
            token_digest=cls.hash_token(raw_token),
            expires_at=timezone.now() + timezone.timedelta(minutes=minutes)
        )
        obj._raw_token = raw_token
        return obj

    @classmethod
    def generate_for_user(cls, user, hours=None, minutes=30, purpose=VerificationPurpose.EMAIL_VERIFY, intended_email=None):
        ttl_minutes = int(hours * 60) if hours is not None else minutes
        return cls.issue_token(
            user=user,
            intended_email=intended_email or user.email,
            purpose=purpose,
            minutes=ttl_minutes,
        )

    @classmethod
    def lookup_by_raw(cls, raw_token: str):
        if not raw_token:
            return None
        digest = cls.hash_token(raw_token)
        return cls.objects.filter(
            models.Q(token_digest=digest) | models.Q(legacy_token=raw_token)
        ).select_related('user', 'onboarding').first()


class LegalDocumentType(models.TextChoices):
    TERMS = 'TERMS', 'Terms of Service'
    PRIVACY = 'PRIVACY', 'Privacy Policy'


class LegalDocumentStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published'


class LegalDocument(models.Model):
    """
    Versioned terms of service and privacy policies with published status and effective dates.
    """
    doc_type = models.CharField(max_length=20, choices=LegalDocumentType.choices)
    version = models.CharField(max_length=20, help_text="e.g. 1.0, 1.1")
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Full markdown or HTML content")
    effective_date = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=LegalDocumentStatus.choices,
        default=LegalDocumentStatus.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('doc_type', 'version')
        ordering = ['-effective_date', '-created_at']
        verbose_name = "Legal Document"
        verbose_name_plural = "Legal Documents"

    def __str__(self):
        return f"{self.get_doc_type_display()} v{self.version} [{self.get_status_display()}]"

    @property
    def is_published(self) -> bool:
        return self.status == LegalDocumentStatus.PUBLISHED

    @classmethod
    def get_active_document(cls, doc_type: str):
        return cls.objects.filter(
            doc_type=doc_type,
            status=LegalDocumentStatus.PUBLISHED
        ).order_by('-effective_date').first()


class LegalAcceptance(models.Model):
    """
    Audit log of which user accepted which document version.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='legal_acceptances')
    document = models.ForeignKey(LegalDocument, on_delete=models.CASCADE, related_name='acceptances')
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-accepted_at']
        verbose_name = "Legal Document Acceptance"
        verbose_name_plural = "Legal Document Acceptances"

    def __str__(self):
        return f"{self.user.username} accepted {self.document.title} (v{self.document.version})"


class OnboardingStep(models.TextChoices):
    PROFILE = 'profile', 'Business Profile'
    PLAN = 'plan', 'Plan & Access'
    WHATSAPP = 'whatsapp', 'WhatsApp Configuration'
    KNOWLEDGE = 'knowledge', 'Knowledge & Catalog'
    TEAM = 'team', 'Team Setup'
    WORKSPACE = 'workspace', 'Sales Workspace'
    TEST = 'test', 'Test & Simulation'
    READINESS = 'readiness', 'Readiness Review'
    COMPLETED = 'completed', 'Completed'


class OnboardingProgress(models.Model):
    """
    Tracks multi-step onboarding wizard progress for a tenant workspace.
    """
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='onboarding_progress')
    current_step = models.CharField(
        max_length=30,
        choices=OnboardingStep.choices,
        default=OnboardingStep.PROFILE
    )
    completed_steps = models.JSONField(default=list, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Onboarding Progress"
        verbose_name_plural = "Onboarding Progresses"

    def __str__(self):
        status = "Completed" if self.is_completed else f"Step: {self.current_step}"
        return f"{self.tenant.name} Onboarding [{status}]"

    def mark_step_done(self, step_name: str, next_step: str = None):
        if step_name not in self.completed_steps:
            self.completed_steps.append(step_name)
        if next_step:
            self.current_step = next_step
        if step_name == OnboardingStep.READINESS or next_step == OnboardingStep.COMPLETED:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.current_step = OnboardingStep.COMPLETED
        self.save()


class DemoRequest(models.Model):
    """
    Public demo / access request for platform operator review.
    Stored at platform level; never automatically routed into any tenant CRM unless explicitly assigned.
    """
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    company_name = models.CharField(max_length=150)
    team_size = models.CharField(max_length=50, blank=True)
    primary_interest = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=[
            ('NEW', 'New Request'),
            ('CONTACTED', 'Contacted / Scheduled'),
            ('PROVISIONED', 'Workspace Provisioned'),
            ('COMPLETED', 'Completed')
        ],
        default='NEW'
    )
    routed_to_tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demo_requests'
    )
    deal = models.ForeignKey(
        'crm.Deal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demo_sources'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Demo Request"
        verbose_name_plural = "Demo Requests"

    def __str__(self):
        return f"Demo: {self.name} ({self.company_name}) [{self.status}]"


class AuditLogAction(models.TextChoices):
    TENANT_CREATED = 'TENANT_CREATED', 'Tenant Created'
    TENANT_STATUS_CHANGED = 'TENANT_STATUS_CHANGED', 'Tenant Status Changed'
    MEMBERSHIP_ADDED = 'MEMBERSHIP_ADDED', 'Membership Added'
    MEMBERSHIP_UPDATED = 'MEMBERSHIP_UPDATED', 'Membership Updated'
    MEMBERSHIP_REVOKED = 'MEMBERSHIP_REVOKED', 'Membership Revoked'
    INVITATION_SENT = 'INVITATION_SENT', 'Invitation Sent'
    CREDENTIALS_UPDATED = 'CREDENTIALS_UPDATED', 'Credentials Updated'
    SUBSCRIPTION_UPDATED = 'SUBSCRIPTION_UPDATED', 'Subscription Updated'
    LEGAL_ACCEPTED = 'LEGAL_ACCEPTED', 'Legal Accepted'
    FEATURE_OVERRIDE_CHANGED = 'FEATURE_OVERRIDE_CHANGED', 'Feature Override Changed'
    BULK_PLAN_ASSIGNED = 'BULK_PLAN_ASSIGNED', 'Bulk Plan Assigned'
    TENANT_INSPECTED = 'TENANT_INSPECTED', 'Tenant Inspected'
    USAGE_LIMIT_EXCEEDED = 'USAGE_LIMIT_EXCEEDED', 'Usage Limit Exceeded'
    STAFF_REQUEST_SUBMITTED = 'STAFF_REQUEST_SUBMITTED', 'Staff Request Submitted'
    STAFF_REQUEST_APPROVED = 'STAFF_REQUEST_APPROVED', 'Staff Request Approved'
    STAFF_REQUEST_REJECTED = 'STAFF_REQUEST_REJECTED', 'Staff Request Rejected'
    ACCOUNT_ACTIVATED = 'ACCOUNT_ACTIVATED', 'Account Activated'
    WORK_REASSIGNED = 'WORK_REASSIGNED', 'Work Reassigned'
    ONBOARDING_REGISTERED = 'ONBOARDING_REGISTERED', 'Client Registration Submitted'
    ONBOARDING_APPROVED = 'ONBOARDING_APPROVED', 'Client Registration Approved'
    ONBOARDING_REJECTED = 'ONBOARDING_REJECTED', 'Client Registration Rejected'
    STAFF_CREATED = 'STAFF_CREATED', 'Staff Account Created'
    STAFF_UPDATED = 'STAFF_UPDATED', 'Staff Account Updated'
    STAFF_PASSWORD_RESET = 'STAFF_PASSWORD_RESET', 'Staff Password Administratively Reset'
    RECOVERY_EMAIL_UPDATED = 'RECOVERY_EMAIL_UPDATED', 'Recovery Email Updated'
    PLATFORM_TICKET_CREATED = 'PLATFORM_TICKET_CREATED', 'Platform Support Ticket Created'
    PLATFORM_TICKET_REPLIED = 'PLATFORM_TICKET_REPLIED', 'Platform Support Ticket Replied'
    PLATFORM_TICKET_STATUS_CHANGED = 'PLATFORM_TICKET_STATUS_CHANGED', 'Platform Support Ticket Status Changed'
    PLATFORM_TICKET_ESCALATED = 'PLATFORM_TICKET_ESCALATED', 'Platform Support Ticket SLA Escalated'
    OPERATOR_ROLE_CHANGED = 'OPERATOR_ROLE_CHANGED', 'Platform Operator Role Changed'
    OUTBOUND_PAUSE_CHANGED = 'OUTBOUND_PAUSE_CHANGED', 'Outbound WhatsApp Pause Changed'
    SYSTEM_SETTINGS_UPDATED = 'SYSTEM_SETTINGS_UPDATED', 'Platform System Settings Updated'
    BILLING_GRACE_UPDATED = 'BILLING_GRACE_UPDATED', 'Billing Grace / Reminder Updated'
    PLAN_LIMITS_UPDATED = 'PLAN_LIMITS_UPDATED', 'Plan Limits Updated'
    CONVERSATION_TRANSFERRED = 'CONVERSATION_TRANSFERRED', 'Conversation Transferred'
    CONTACTS_IMPORTED = 'CONTACTS_IMPORTED', 'Contacts CSV Imported'


class TenantAuditLog(models.Model):
    """
    Security audit trail of privilege, tenant status, and configuration events.
    Never logs secrets or sensitive values.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_actions')
    action = models.CharField(max_length=40, choices=AuditLogAction.choices)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tenant Audit Log"
        verbose_name_plural = "Tenant Audit Logs"

    def __str__(self):
        tenant_str = self.tenant.name if self.tenant else "Platform"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {tenant_str} - {self.action}: {self.summary}"


class PlatformOperatorRole(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
    SUPPORT = 'SUPPORT', 'Platform Support'
    BILLING = 'BILLING', 'Billing & Accounts'
    READ_ONLY = 'READ_ONLY', 'Read-Only Observer'


class UserSecurityProfile(models.Model):
    """
    Tracks email verification, internal synthetic identifiers, recovery addresses,
    and security state for identities.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security_profile')
    platform_role = models.CharField(
        max_length=20,
        choices=PlatformOperatorRole.choices,
        blank=True,
        default='',
        help_text="Least-privilege role for platform operators (empty defaults to SUPER_ADMIN for legacy superusers)",
    )
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    is_trusted_seed = models.BooleanField(default=False)
    internal_identifier = models.CharField(max_length=254, unique=True, null=True, blank=True)
    is_synthetic_identifier = models.BooleanField(default=False)
    skip_mailbox_gate = models.BooleanField(default=False)
    recovery_email = models.EmailField(max_length=254, blank=True, default='')
    recovery_email_verified = models.BooleanField(default=False)
    recovery_email_verified_at = models.DateTimeField(null=True, blank=True)
    pending_recovery_email = models.EmailField(max_length=254, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Security Profile"
        verbose_name_plural = "User Security Profiles"

    def __str__(self):
        status = "Verified" if self.email_verified else "Unverified"
        return f"{self.user.username} [{status}]"

    @classmethod
    def get_or_create_for_user(cls, user):
        default_verified = bool(user.is_superuser or user.is_staff)
        real_email = (user.email or '').strip()
        profile, _ = cls.objects.get_or_create(
            user=user,
            defaults={
                'email_verified': default_verified,
                'email_verified_at': timezone.now() if default_verified else None,
                'is_trusted_seed': default_verified,
                'recovery_email': real_email if (default_verified and real_email) else '',
                'recovery_email_verified': bool(default_verified and real_email),
                'recovery_email_verified_at': timezone.now() if (default_verified and real_email) else None,
            }
        )
        return profile


class OverrideChoice(models.TextChoices):
    INHERIT = 'INHERIT', 'Inherit from Plan'
    ALLOW = 'ALLOW', 'Explicit Allow'
    DENY = 'DENY', 'Explicit Deny'


class TenantFeatureOverride(models.Model):
    """
    Tenant-specific capability override configured by platform superadmin.
    Precedence: Deny overrides Plan; Allow overrides Plan only when granted by Platform Admin.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='feature_overrides')
    feature_key = models.CharField(max_length=80, help_text="Module or capability key")
    override = models.CharField(max_length=15, choices=OverrideChoice.choices, default=OverrideChoice.INHERIT)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant Feature Override"
        verbose_name_plural = "Tenant Feature Overrides"
        unique_together = ('tenant', 'feature_key')

    def __str__(self):
        return f"{self.tenant.name} -> {self.feature_key} [{self.override}]"


class TenantMonthlyUsage(models.Model):
    """
    Tracks monthly message throughput against subscription allowances.
    Billing period boundaries: Calendar month (1st of month 00:00 UTC).
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='monthly_usages')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    outbound_messages_sent = models.PositiveIntegerField(default=0)
    outbound_messages_attempted = models.PositiveIntegerField(default=0)
    outbound_messages_reserved = models.PositiveIntegerField(default=0)
    inbound_messages_received = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant Monthly Usage"
        verbose_name_plural = "Tenant Monthly Usages"
        unique_together = ('tenant', 'year', 'month')

    def __str__(self):
        return f"{self.tenant.name} ({self.year}-{self.month:02d}): {self.outbound_messages_sent} sent"

class SavedReply(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='saved_replies')
    title = models.CharField(max_length=100)
    body = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant','title'], name='unique_tenant_reply_title')]


class PlatformServiceConfig(models.Model):
    """Software-provider configuration. Secret values are encrypted separately."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    smtp_enabled = models.BooleanField(default=False)
    smtp_host = models.CharField(max_length=253, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=254, blank=True)
    smtp_from_email = models.EmailField(blank=True)
    smtp_security = models.CharField(max_length=10, default='TLS')
    encrypted_secrets = models.TextField(blank=True)
    verification_expiry_minutes = models.PositiveSmallIntegerField(default=30)
    resend_cooldown_seconds = models.PositiveSmallIntegerField(default=60)
    resend_max_per_hour = models.PositiveSmallIntegerField(default=5)
    support_alert_email = models.EmailField(default='support@neorizsolutions.com')
    support_escalation_minutes = models.PositiveSmallIntegerField(default=10)
    global_outbound_paused = models.BooleanField(default=False)
    global_outbound_pause_reason = models.CharField(max_length=255, blank=True, default='')
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.CharField(
        max_length=255,
        blank=True,
        default='Scheduled maintenance is in progress. Please try again shortly.',
    )
    last_backup_verified_at = models.DateTimeField(null=True, blank=True)
    last_backup_note = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)


class TransactionalEmail(models.Model):
    """Durable email outbox. Acknowledgement means SMTP acceptance, not inbox delivery."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    onboarding = models.ForeignKey(ClientOnboarding, on_delete=models.CASCADE, null=True, blank=True, related_name='emails')
    activation_token = models.ForeignKey(AccountActivationToken, on_delete=models.CASCADE, null=True, blank=True)
    verification_token = models.ForeignKey(EmailVerificationToken, on_delete=models.CASCADE, null=True, blank=True)
    purpose = models.CharField(max_length=32, default='ACTIVATION')
    recipient = models.EmailField()
    encrypted_payload = models.TextField()
    dedup_key = models.CharField(max_length=180, unique=True)
    status = models.CharField(max_length=30, default='PENDING', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)
    provider_message_id = models.CharField(max_length=180, blank=True, default='')
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ManualBillingEntry(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='manual_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    reference = models.CharField(max_length=100)
    received_on = models.DateField()
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant','reference'], name='unique_manual_payment_reference')]

class RecoveryThrottle(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)


class PlatformTicketStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    AWAITING_PLATFORM = 'AWAITING_PLATFORM', 'Awaiting Platform'
    AWAITING_CLIENT = 'AWAITING_CLIENT', 'Awaiting Client'
    RESOLVED = 'RESOLVED', 'Resolved'
    CLOSED = 'CLOSED', 'Closed'


class PlatformTicketPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class PlatformTicketCategory(models.TextChoices):
    META_SETUP = 'META_SETUP', 'Meta & WhatsApp Setup'
    BILLING = 'BILLING', 'Billing & Subscription'
    WHATSAPP_DELIVERY = 'WHATSAPP_DELIVERY', 'WhatsApp Delivery & Webhooks'
    ACCOUNT = 'ACCOUNT', 'Account, Email & Staff Access'
    BUG = 'BUG', 'Platform Bug / Outage'
    OTHER = 'OTHER', 'Other Platform Help'


class PlatformSupportTicket(models.Model):
    """
    Client-to-Platform SaaS Support ticket (strictly separate from tenant CRM customer SupportTicket).
    Tracks unanswered client message SLA cycles cleanly so ten-minute escalation alerts
    fire once per unanswered wait cycle and cannot be reset by follow-up client messages.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket_number = models.CharField(max_length=24, unique=True, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='platform_support_tickets')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_platform_tickets')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_platform_tickets')
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=32, choices=PlatformTicketCategory.choices, default=PlatformTicketCategory.META_SETUP)
    priority = models.CharField(max_length=16, choices=PlatformTicketPriority.choices, default=PlatformTicketPriority.NORMAL)
    status = models.CharField(max_length=24, choices=PlatformTicketStatus.choices, default=PlatformTicketStatus.OPEN, db_index=True)

    sla_cycle_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    current_cycle_escalated = models.BooleanField(default=False)
    last_client_message_at = models.DateTimeField(null=True, blank=True)
    first_platform_reply_at = models.DateTimeField(null=True, blank=True)
    last_platform_reply_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    escalations_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Platform Support Ticket"
        verbose_name_plural = "Platform Support Tickets"

    def __str__(self):
        return f"{self.ticket_number} [{self.status}] {self.subject}"


class PlatformTicketSenderType(models.TextChoices):
    CLIENT = 'CLIENT', 'Client User'
    PLATFORM = 'PLATFORM', 'Platform Operator'
    SYSTEM = 'SYSTEM', 'System Notice'


class PlatformSupportMessage(models.Model):
    """
    Message or internal operator note on a PlatformSupportTicket.
    Internal notes (is_internal_note=True) are strictly hidden from client views/APIs
    and NEVER clear or satisfy the client response SLA.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(PlatformSupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='platform_support_messages')
    sender_type = models.CharField(max_length=16, choices=PlatformTicketSenderType.choices, default=PlatformTicketSenderType.CLIENT)
    is_internal_note = models.BooleanField(default=False, db_index=True)
    body = models.TextField()
    attachment_name = models.CharField(max_length=200, blank=True, default='')
    attachment_key = models.CharField(max_length=300, blank=True, default='')
    attachment_mime = models.CharField(max_length=80, blank=True, default='')
    attachment_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Platform Support Message"
        verbose_name_plural = "Platform Support Messages"


class PlatformSupportEscalation(models.Model):
    """
    Durable audit and deduplication record for 10-minute SLA emergency escalations.
    Enforces a DB-level UniqueConstraint per (ticket, cycle_started_at) so concurrent workers
    never send duplicate emergency alerts for the same unanswered client wait cycle.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(PlatformSupportTicket, on_delete=models.CASCADE, related_name='escalations')
    cycle_started_at = models.DateTimeField()
    escalated_to_email = models.EmailField(max_length=254, default='support@neorizsolutions.com')
    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending Dispatch'),
            ('SENT', 'Dispatched via SMTP'),
            ('CANCELLED', 'Cancelled Before Send'),
            ('FAILED', 'Delivery Failed'),
        ],
        default='PENDING',
        db_index=True,
    )
    email_job = models.ForeignKey(TransactionalEmail, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_escalations')
    reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'cycle_started_at'], name='unique_support_escalation_per_cycle'),
        ]
        verbose_name = "Platform Support Escalation"
        verbose_name_plural = "Platform Support Escalations"
