from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class Company(models.Model):
    """
    Tenant-scoped Company or Organization representing customer businesses.
    Distinct from the SaaS Tenant model.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='companies'
    )
    name = models.CharField(max_length=180, help_text="Company or organization legal/brand name")
    domain = models.CharField(max_length=150, blank=True, default='', help_text="Company website or domain (e.g. acme.com)")
    phone = models.CharField(max_length=30, blank=True, default='', help_text="Primary company phone number")
    address = models.TextField(blank=True, default='', help_text="Company physical or registered address")
    industry = models.CharField(max_length=100, blank=True, default='', help_text="Industry sector (e.g. Retail, Healthcare, IT)")
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_companies',
        help_text="Tenant staff member owning this company relationship"
    )
    notes = models.TextField(blank=True, default='', help_text="Internal account notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        unique_together = ('tenant', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} [{self.tenant.name if self.tenant else 'No Tenant'}]"

    def clean(self):
        super().clean()
        if self.owner and self.tenant and not self.owner.is_superuser:
            if not self.tenant.memberships.filter(user=self.owner, is_active=True).exists():
                raise ValidationError("Company owner must be an active member of this tenant.")


class Pipeline(models.Model):
    """
    Tenant-configurable sales pipeline containing ordered stages.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='crm_pipelines'
    )
    name = models.CharField(max_length=100, help_text="e.g. 'Standard Sales', 'Enterprise', 'Inbound WhatsApp'")
    is_default = models.BooleanField(default=False, help_text="Designates this pipeline as the primary default for new deals")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pipeline"
        verbose_name_plural = "Pipelines"
        ordering = ['-is_default', 'name']

    def __str__(self):
        default_str = " (Default)" if self.is_default else ""
        return f"{self.name}{default_str} - {self.tenant.name if self.tenant else ''}"

    def save(self, *args, **kwargs):
        if self.is_default:
            # Ensure only one default pipeline per tenant
            Pipeline.objects.filter(tenant=self.tenant, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_default(cls, tenant):
        """Returns or provisions the default sales pipeline with initial ordered stages."""
        pipeline = cls.objects.filter(tenant=tenant, is_default=True).first()
        if not pipeline:
            pipeline = cls.objects.filter(tenant=tenant).first()
        if not pipeline:
            pipeline = cls.objects.create(
                tenant=tenant,
                name="Default Sales Pipeline",
                is_default=True,
                is_active=True
            )
            # Create standard default stages
            initial_stages = [
                ("New", 1, 10, False, False),
                ("Qualified", 2, 25, False, False),
                ("Demo / Consultation", 3, 50, False, False),
                ("Proposal", 4, 70, False, False),
                ("Negotiation", 5, 85, False, False),
                ("Closed Won", 6, 100, True, False),
                ("Closed Lost", 7, 0, False, True),
            ]
            for sname, sorder, sprob, swon, slost in initial_stages:
                DealStage.objects.create(
                    pipeline=pipeline,
                    name=sname,
                    order=sorder,
                    probability=sprob,
                    is_won=swon,
                    is_lost=slost
                )
        return pipeline


class DealStage(models.Model):
    """
    Ordered stage within a specific Pipeline.
    """
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name='stages'
    )
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=1, help_text="Stage sequence order in pipeline")
    probability = models.PositiveSmallIntegerField(default=10, help_text="Default win probability percentage (0-100)")
    is_won = models.BooleanField(default=False, help_text="Terminal stage indicating successful deal close")
    is_lost = models.BooleanField(default=False, help_text="Terminal stage indicating lost opportunity")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deal Stage"
        verbose_name_plural = "Deal Stages"
        ordering = ['order', 'id']
        unique_together = ('pipeline', 'name')

    def __str__(self):
        return f"{self.pipeline.name} → {self.name} ({self.probability}%)"

    def clean(self):
        super().clean()
        if self.is_won and self.is_lost:
            raise ValidationError("A stage cannot be marked as both Won and Lost simultaneously.")


class Deal(models.Model):
    """
    Sales opportunity tracked within a pipeline and stage.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='deals'
    )
    title = models.CharField(max_length=200, help_text="Descriptive deal title (e.g. 'Cafe Website + TABLO POS')")
    contact = models.ForeignKey(
        'chatbot.Customer',
        on_delete=models.CASCADE,
        related_name='deals',
        help_text="Primary person/contact record"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals',
        help_text="Associated company/organization"
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_deals',
        help_text="Assigned deal owner from tenant members"
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.PROTECT,
        related_name='deals'
    )
    stage = models.ForeignKey(
        DealStage,
        on_delete=models.PROTECT,
        related_name='deals'
    )
    product = models.ForeignKey(
        'business.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals',
        help_text="Linked verified product if applicable"
    )
    service = models.ForeignKey(
        'services.Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deals',
        help_text="Linked agency service if applicable"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated deal value. Never infer from unapproved catalog prices."
    )
    currency = models.CharField(max_length=10, default='INR', help_text="ISO currency code (e.g. INR, USD, AED)")
    expected_close_date = models.DateField(null=True, blank=True, help_text="Target deal closing date")
    probability = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Win probability percentage (defaults to stage probability if unset)"
    )
    requirements_summary = models.TextField(blank=True, default='', help_text="Captured customer requirements or scope notes")
    won_at = models.DateTimeField(null=True, blank=True)
    lost_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.TextField(blank=True, default='', help_text="Reason recorded when deal is marked lost")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deal"
        verbose_name_plural = "Deals"
        ordering = ['-updated_at']

    def __str__(self):
        amt_str = f" ({self.currency} {self.amount})" if self.amount else ""
        return f"{self.title}{amt_str} [{self.stage.name}]"

    def clean(self):
        super().clean()
        # Tenant isolation validations
        if self.contact and self.tenant and self.contact.tenant_id != self.tenant_id:
            raise ValidationError("Contact must belong to the same tenant as the deal.")
        if self.company and self.tenant and self.company.tenant_id != self.tenant_id:
            raise ValidationError("Company must belong to the same tenant as the deal.")
        if self.pipeline and self.tenant and self.pipeline.tenant_id != self.tenant_id:
            raise ValidationError("Pipeline must belong to the same tenant as the deal.")
        if self.stage and self.pipeline and self.stage.pipeline_id != self.pipeline_id:
            raise ValidationError("Stage must belong to the selected Pipeline.")
        if self.product and self.tenant and self.product.tenant_id != self.tenant_id:
            raise ValidationError("Product must belong to the same tenant as the deal.")
        if self.service and self.tenant and self.service.tenant_id != self.tenant_id:
            raise ValidationError("Service must belong to the same tenant as the deal.")
        if self.owner and self.tenant and not self.owner.is_superuser:
            if not self.tenant.memberships.filter(user=self.owner, is_active=True).exists():
                raise ValidationError("Deal owner must be an active member of this tenant.")

    def save(self, *args, **kwargs):
        if self.probability is None and self.stage_id and self.stage:
            self.probability = self.stage.probability
        # Terminal state tracking
        if self.stage_id and self.stage and self.stage.is_won and not self.won_at:
            self.won_at = timezone.now()
            self.lost_at = None
        elif self.stage_id and self.stage and self.stage.is_lost and not self.lost_at:
            self.lost_at = timezone.now()
            self.won_at = None
        elif self.stage_id and self.stage and not self.stage.is_won and not self.stage.is_lost:
            self.won_at = None
            self.lost_at = None
        super().save(*args, **kwargs)

    @property
    def is_closed(self) -> bool:
        return bool((self.stage and (self.stage.is_won or self.stage.is_lost)) or self.won_at or self.lost_at)

    @property
    def weighted_value(self):
        if self.amount is not None:
            prob = self.probability if self.probability is not None else (self.stage.probability if self.stage else 0)
            return (self.amount * prob) / 100
        return None

    @property
    def next_activity(self):
        return self.activities.filter(status=ActivityStatus.PENDING).order_by('due_date').first()


class DealStageHistory(models.Model):
    """
    Immutable audit trail of deal stage transitions.
    """
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='stage_history')
    from_stage = models.ForeignKey(DealStage, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    to_stage = models.ForeignKey(DealStage, on_delete=models.CASCADE, related_name='+')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deal Stage History"
        verbose_name_plural = "Deal Stage History"
        ordering = ['-created_at']

    def __str__(self):
        from_str = self.from_stage.name if self.from_stage else 'Start'
        return f"{self.deal.title}: {from_str} → {self.to_stage.name} at {self.created_at:%Y-%m-%d %H:%M}"


class ActivityType(models.TextChoices):
    CALL = 'CALL', 'Phone Call'
    MEETING = 'MEETING', 'Meeting'
    DEMO = 'DEMO', 'Product Demo'
    FOLLOW_UP = 'FOLLOW_UP', 'Follow Up'
    TASK = 'TASK', 'General Task'


class ActivityStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class ActivityPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'


class Activity(models.Model):
    """
    Task or planned interaction linked to a Contact, Deal, or Company.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='activities'
    )
    activity_type = models.CharField(
        max_length=20,
        choices=ActivityType.choices,
        default=ActivityType.TASK
    )
    title = models.CharField(max_length=200, help_text="Activity description / subject")
    notes = models.TextField(blank=True, default='', help_text="Detailed notes or agenda")
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crm_activities',
        help_text="Assigned tenant member"
    )
    due_date = models.DateTimeField(null=True, blank=True, help_text="Due date and time (timezone aware)")
    status = models.CharField(
        max_length=20,
        choices=ActivityStatus.choices,
        default=ActivityStatus.PENDING,
        db_index=True
    )
    priority = models.CharField(
        max_length=15,
        choices=ActivityPriority.choices,
        default=ActivityPriority.MEDIUM
    )
    contact = models.ForeignKey(
        'chatbot.Customer',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='activities'
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities'
    )
    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='activities'
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activity"
        verbose_name_plural = "Activities"
        ordering = ['due_date', '-priority']

    def __str__(self):
        due_str = f" (Due: {self.due_date:%Y-%m-%d %H:%M})" if self.due_date else ""
        return f"[{self.get_activity_type_display()}] {self.title}{due_str} - {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.contact and self.tenant and self.contact.tenant_id != self.tenant_id:
            raise ValidationError("Contact must belong to the same tenant as the activity.")
        if self.company and self.tenant and self.company.tenant_id != self.tenant_id:
            raise ValidationError("Company must belong to the same tenant as the activity.")
        if self.deal and self.tenant and self.deal.tenant_id != self.tenant_id:
            raise ValidationError("Deal must belong to the same tenant as the activity.")
        if self.assigned_to and self.tenant and not self.assigned_to.is_superuser:
            if not self.tenant.memberships.filter(user=self.assigned_to, is_active=True).exists():
                raise ValidationError("Assignee must be an active member of this tenant.")

    @property
    def is_overdue(self) -> bool:
        return bool(self.status == ActivityStatus.PENDING and self.due_date and self.due_date < timezone.now())

    def mark_completed(self, user=None):
        self.status = ActivityStatus.COMPLETED
        self.completed_at = timezone.now()
        if user:
            self.completed_by = user
        self.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])


class ContactNote(models.Model):
    """
    Internal staff notes on a contact, kept strictly separate from WhatsApp messages sent to customers.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='contact_notes'
    )
    contact = models.ForeignKey(
        'chatbot.Customer',
        on_delete=models.CASCADE,
        related_name='internal_notes'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    content = models.TextField(help_text="Internal confidential notes regarding this contact")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contact Note"
        verbose_name_plural = "Contact Notes"
        ordering = ['-created_at']

    def __str__(self):
        author_name = self.author.username if self.author else 'System'
        return f"Note by @{author_name} for {self.contact.name or self.contact.phone_number} on {self.created_at:%Y-%m-%d}"

    def clean(self):
        super().clean()
        if self.contact and self.tenant and self.contact.tenant_id != self.tenant_id:
            raise ValidationError("Contact must belong to the same tenant as the note.")


class ContactMergeAudit(models.Model):
    """
    Audit log of explicit contact record merges to preserve auditability and trace duplicate consolidation.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='merge_audits'
    )
    primary_contact = models.ForeignKey(
        'chatbot.Customer',
        on_delete=models.CASCADE,
        related_name='merge_records'
    )
    merged_phone = models.CharField(max_length=30)
    merged_name = models.CharField(max_length=150, blank=True)
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    details = models.JSONField(default=dict, help_text="Summary of transferred deals, messages, and activities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contact Merge Audit"
        verbose_name_plural = "Contact Merge Audits"
        ordering = ['-created_at']

    def __str__(self):
        return f"Merged {self.merged_phone} into #{self.primary_contact_id} by @{self.performed_by.username if self.performed_by else 'System'}"


# ============================================================================
# 1. QUOTATIONS AND PROPOSALS
# ============================================================================

class QuoteStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SENT = 'SENT', 'Sent to Customer'
    APPROVED = 'APPROVED', 'Approved / Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    EXPIRED = 'EXPIRED', 'Expired'


class Quote(models.Model):
    """
    Versioned, deal-linked price quotation with decimal amounts and line items.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='quotes'
    )
    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name='quotes'
    )
    quote_number = models.CharField(max_length=60, help_text="e.g. QT-2026-0001")
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, help_text="Quotation subject or proposal title")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18.0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=20, choices=QuoteStatus.choices, default=QuoteStatus.DRAFT)
    terms_and_conditions = models.TextField(blank=True, default='')
    valid_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quote"
        verbose_name_plural = "Quotes"
        ordering = ['-created_at']
        unique_together = ('tenant', 'quote_number', 'version')

    def __str__(self):
        return f"{self.quote_number} v{self.version} - {self.title} ({self.currency} {self.total_amount})"

    def clean(self):
        super().clean()
        if self.deal and self.tenant and self.deal.tenant_id != self.tenant_id:
            raise ValidationError("Deal must belong to the same tenant as the quote.")

    def recalculate_totals(self):
        """Idempotently recalculates quote subtotal, tax, and total based on line items."""
        from decimal import Decimal
        items = self.items.all()
        sub = sum(item.total_price for item in items)
        self.subtotal = sub
        taxable = max(Decimal('0'), sub - (self.discount_amount or Decimal('0')))
        tax_rate = Decimal(str(self.tax_percent or 0)) / Decimal('100')
        self.tax_amount = (taxable * tax_rate).quantize(Decimal('0.01'))
        self.total_amount = taxable + self.tax_amount
        self.save(update_fields=['subtotal', 'discount_amount', 'tax_percent', 'tax_amount', 'total_amount', 'updated_at'])


class QuoteItem(models.Model):
    """
    Individual line item in a versioned quote.
    """
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey('business.Product', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        from decimal import Decimal
        gross = Decimal(str(self.quantity or 1)) * Decimal(str(self.unit_price or 0))
        disc_rate = Decimal(str(self.discount_percent or 0)) / Decimal('100')
        disc = gross * disc_rate
        self.total_price = (gross - disc).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 2. LEAD QUALIFICATION AND EXPLAINABLE SCORING
# ============================================================================

class QualificationQuestion(models.Model):
    """
    Tenant-configurable qualification questions by service/product.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='qualification_questions')
    product = models.ForeignKey('business.Product', on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True)
    question_text = models.CharField(max_length=255)
    field_key = models.CharField(max_length=60, help_text="e.g. 'budget_range', 'timeline', 'company_size'")
    is_required = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ('tenant', 'field_key')

    def __str__(self):
        return f"{self.field_key}: {self.question_text}"


class LeadQualificationAnswer(models.Model):
    """
    Progressively captured qualification details linked to a contact/deal.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='qualification_answers')
    contact = models.ForeignKey('chatbot.Customer', on_delete=models.CASCADE, related_name='qualification_answers')
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name='qualification_answers')
    question = models.ForeignKey(QualificationQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField()
    source_message = models.TextField(blank=True, default='', help_text="WhatsApp or portal message snippet providing evidence")
    is_verified_by_human = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('contact', 'question')


class LeadScorePriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class LeadScore(models.Model):
    """
    Explainable rule-based lead priority score with visible score breakdown.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='lead_scores')
    contact = models.OneToOneField('chatbot.Customer', on_delete=models.CASCADE, related_name='lead_score')
    score = models.PositiveSmallIntegerField(default=10, help_text="Score from 0 to 100")
    priority = models.CharField(max_length=15, choices=LeadScorePriority.choices, default=LeadScorePriority.MEDIUM)
    score_breakdown = models.JSONField(default=dict, help_text="Visible contributions, e.g. {'recency': 20, 'budget': 30}")
    rule_version = models.CharField(max_length=20, default='v1.0')
    is_manual_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True, default='')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_score(self):
        """Computes deterministic, explainable lead priority score."""
        if self.is_manual_override:
            return self.score
        breakdown = {}
        total = 0
        
        # 1. Completeness of contact profile
        completeness = 0
        if self.contact.email:
            completeness += 15
        if self.contact.company:
            completeness += 20
        if self.contact.name:
            completeness += 10
        breakdown['profile_completeness'] = completeness
        total += completeness

        # 2. Qualification answers count
        q_count = self.contact.qualification_answers.count()
        q_score = min(30, q_count * 10)
        breakdown['qualification_answers'] = q_score
        total += q_score

        # 3. Active deal value
        deal = self.contact.deals.first()
        if deal and deal.amount:
            deal_score = 25 if deal.amount > 50000 else 15
            breakdown['deal_value'] = deal_score
            total += deal_score

        self.score = min(100, total)
        if self.score >= 75:
            self.priority = LeadScorePriority.URGENT
        elif self.score >= 50:
            self.priority = LeadScorePriority.HIGH
        elif self.score >= 25:
            self.priority = LeadScorePriority.MEDIUM
        else:
            self.priority = LeadScorePriority.LOW

        self.score_breakdown = breakdown
        return self.score


# ============================================================================
# 3. WORKFLOW AUTOMATION ENGINE
# ============================================================================

class AutomationTrigger(models.TextChoices):
    NEW_ENQUIRY = 'lead.created', 'New Enquiry'
    ASSIGNMENT_CHANGED = 'lead.assigned', 'Assignment Changed'
    QUALIFICATION_COMPLETED = 'qualification.completed', 'Qualification Completed'
    STAGE_CHANGED = 'deal.stage_changed', 'Deal Stage Changed'
    TASK_OVERDUE = 'task.overdue', 'Task Overdue'
    CONVERSATION_CLOSED = 'conversation.closed', 'Conversation Closed'
    DEAL_WON = 'deal.won', 'Deal Won'
    DEAL_LOST = 'deal.lost', 'Deal Lost'
    TICKET_CREATED = 'ticket.created', 'Support Ticket Created'
    FIRST_INBOUND = 'conversation.first_inbound', 'New Customer Greeting'
    OUTSIDE_BUSINESS_HOURS = 'conversation.after_hours', 'Outside Business Hours'
    NO_RESPONSE_SLA = 'conversation.no_response', 'Unanswered Chat Follow-up'


class AutomationActionType(models.TextChoices):
    ASSIGN_STAFF = 'ASSIGN_STAFF', 'Assign Eligible Staff'
    CREATE_TASK = 'CREATE_TASK', 'Create Follow-up Task'
    ADD_INTERNAL_NOTE = 'ADD_INTERNAL_NOTE', 'Add Internal Note'
    CREATE_ONBOARDING = 'CREATE_ONBOARDING', 'Create Onboarding Checklist'
    UPDATE_STAGE = 'UPDATE_STAGE', 'Update Deal Stage'
    ESCALATE = 'ESCALATE', 'Escalate to Manager'
    AUTO_REPLY = 'AUTO_REPLY', 'Send Automated WhatsApp Reply'


class AutomationRule(models.Model):
    """
    Tenant-scoped workflow automation rule with trigger conditions and action parameters.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='automation_rules')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    trigger_type = models.CharField(max_length=50, choices=AutomationTrigger.choices)
    conditions = models.JSONField(default=dict, help_text="e.g. {'stage_name': 'Closed Won'}")
    action_type = models.CharField(max_length=50, choices=AutomationActionType.choices)
    action_config = models.JSONField(default=dict, help_text="e.g. {'task_title': 'Prepare contract', 'due_days': 2}")
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    execution_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} [{self.trigger_type} → {self.action_type}]"


class BusinessEvent(models.Model):
    """
    Durable Outbox Event record representing an authoritative business state transition.
    Persisted atomically in the same transaction as the business mutation, then processed
    idempotently by the automation engine and outbound webhook queue.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='business_events')
    event_id = models.CharField(max_length=64, unique=True, db_index=True)
    event_type = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    dedup_key = models.CharField(max_length=128, unique=True, null=True, blank=True, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    causation_id = models.CharField(max_length=64, blank=True, db_index=True)
    causation_depth = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        default='PENDING',
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('PROCESSED', 'Processed'),
            ('FAILED', 'Failed'),
            ('DEAD_LETTER', 'Dead Letter'),
        ],
        db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claim_token = models.CharField(max_length=64, blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['tenant', 'status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.event_type} [{self.event_id[:8]}] - {self.status}"


class AutomationRunLog(models.Model):
    """
    Execution history and audit trail for automated workflow runs.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='automation_run_logs')
    rule = models.ForeignKey(AutomationRule, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.ForeignKey(BusinessEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name='automation_runs')
    trigger_event = models.CharField(max_length=60)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('CLAIMED', 'Claimed'),
            ('SUCCESS', 'Success'),
            ('SKIPPED', 'Skipped'),
            ('FAILED', 'Failed'),
            ('DEAD_LETTER', 'Dead Letter'),
        ]
    )
    details = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True)
    causation_id = models.CharField(max_length=64, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=1)
    execution_lease_expires_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-executed_at']


# ============================================================================
# 4. CUSTOMER SUPPORT TICKETS AND POST-SALE ONBOARDING
# ============================================================================

class TicketPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class TicketStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    WAITING_CUSTOMER = 'WAITING_CUSTOMER', 'Waiting on Customer'
    RESOLVED = 'RESOLVED', 'Resolved'
    CLOSED = 'CLOSED', 'Closed'


class SupportTicket(models.Model):
    """
    Customer support ticket linked to contact, conversation, or deal.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='support_tickets')
    ticket_number = models.CharField(max_length=40, help_text="e.g. TICK-1001")
    contact = models.ForeignKey('chatbot.Customer', on_delete=models.CASCADE, related_name='support_tickets')
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets')
    deal = models.ForeignKey(Deal, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(
        max_length=40,
        default='GENERAL',
        choices=[
            ('TECHNICAL', 'Technical Issue'),
            ('BILLING', 'Billing & Invoicing'),
            ('ONBOARDING', 'Post-Sale Onboarding'),
            ('GENERAL', 'General Inquiry'),
        ]
    )
    priority = models.CharField(max_length=20, choices=TicketPriority.choices, default=TicketPriority.MEDIUM)
    status = models.CharField(max_length=25, choices=TicketStatus.choices, default=TicketStatus.OPEN)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    response_target_hours = models.PositiveSmallIntegerField(default=24)
    resolution_reason = models.TextField(blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('tenant', 'ticket_number')

    def __str__(self):
        return f"{self.ticket_number}: {self.subject} [{self.get_status_display()}]"


class TicketNote(models.Model):
    """
    Internal notes and communication log within a support ticket.
    """
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    is_internal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OnboardingChecklist(models.Model):
    """
    Post-sale onboarding checklist for newly won customer deals.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='onboarding_checklists')
    deal = models.OneToOneField(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name='onboarding_checklist')
    contact = models.ForeignKey('chatbot.Customer', on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    target_completion_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({'Completed' if self.is_completed else 'In Progress'})"


class OnboardingTask(models.Model):
    """
    Specific actionable item in an onboarding checklist.
    """
    checklist = models.ForeignKey(OnboardingChecklist, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=1)
    is_done = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['order', 'id']


# ============================================================================
# 5. GROWTH TOOLS AND CONSENT-AWARE OUTREACH
# ============================================================================

class ConsentSource(models.TextChoices):
    WHATSAPP_INBOUND = 'WHATSAPP_INBOUND', 'WhatsApp Inbound Message'
    WEBSITE_FORM = 'WEBSITE_FORM', 'Website Form Checkbox'
    VERBAL = 'VERBAL', 'Verbal / Phone Consultation'
    PORTAL = 'PORTAL', 'Customer Portal'


class ContactConsent(models.Model):
    """
    Consent tracking and suppression state for outbound messaging.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='contact_consents')
    contact = models.OneToOneField('chatbot.Customer', on_delete=models.CASCADE, related_name='consent_record')
    has_consented = models.BooleanField(default=False)
    marketing_allowed = models.BooleanField(default=False)
    utility_allowed = models.BooleanField(default=False)
    source = models.CharField(max_length=30, choices=ConsentSource.choices, default=ConsentSource.WHATSAPP_INBOUND)
    purpose = models.CharField(max_length=100, default='Transactional and updates')
    evidence_text = models.TextField(blank=True, default='')
    is_opted_out = models.BooleanField(default=False, help_text="Suppression state: prevents any outbound marketing dispatch")
    opted_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "Opted-Out" if self.is_opted_out else ("Consented" if self.has_consented else "Unconfirmed")
        return f"Consent: {self.contact.phone_number} [{status}]"


class WhatsAppTemplate(models.Model):
    """
    Meta-approved WhatsApp message template metadata.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='whatsapp_templates')
    name = models.CharField(max_length=100, help_text="Template name in Meta Business Manager")
    category = models.CharField(max_length=30, default='UTILITY', choices=[('UTILITY', 'Utility'), ('MARKETING', 'Marketing'), ('AUTHENTICATION', 'Authentication')])
    language = models.CharField(max_length=15, default='en')
    body_text = models.TextField()
    variables = models.JSONField(default=list, help_text="List of required variable placeholder names")
    meta_status = models.CharField(
        max_length=20,
        default='DRAFT',
        choices=[
            ('APPROVED', 'Approved'),
            ('PENDING', 'Pending Review'),
            ('REJECTED', 'Rejected'),
            ('DRAFT', 'Local Draft'),
            ('PAUSED', 'Paused'),
        ]
    )
    meta_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    submission_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'name', 'language')

    def __str__(self):
        return f"{self.name} ({self.language}) [{self.meta_status}]"


class CampaignRecipient(models.Model):
    """Immutable audience membership; one durable delivery per campaign/contact."""
    campaign = models.ForeignKey('Campaign', on_delete=models.CASCADE, related_name='recipients')
    contact = models.ForeignKey('chatbot.Customer', on_delete=models.CASCADE)
    delivery = models.OneToOneField('whatsapp.WhatsAppDelivery', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default='PENDING')
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['campaign', 'contact'], name='unique_campaign_contact')]


class Campaign(models.Model):
    """
    Consent-aware outbound broadcast draft with audience preview and safety gates.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=150)
    template = models.ForeignKey(WhatsAppTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=25,
        default='DRAFT',
        choices=[
            ('DRAFT', 'Draft'),
            ('SCHEDULED', 'Scheduled'),
            ('RUNNING', 'Running'),
            ('PAUSED', 'Paused'),
            ('COMPLETED', 'Completed'),
            ('CANCELLED', 'Cancelled'),
        ]
    )
    target_lifecycle_status = models.CharField(max_length=30, blank=True, default='')
    target_tags = models.JSONField(default=list, blank=True)
    template_parameters = models.JSONField(default=list, blank=True)
    variable_mapping = models.JSONField(default=list, blank=True)
    launched_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    audience_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} [{self.status}]"


# ============================================================================
# 6. INTEGRATION CENTRE AND SIGNED OUTBOUND WEBHOOKS
# ============================================================================

class WebhookEndpoint(models.Model):
    """
    Tenant-scoped signed outbound webhook destination with HMAC signing.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='webhook_endpoints')
    target_url = models.URLField(max_length=500)
    signing_secret = models.CharField(max_length=128, help_text="Secret key used for HMAC-SHA256 signature")
    subscribed_events = models.JSONField(default=list, help_text="e.g. ['lead.created', 'deal.won', 'ticket.created']")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        # SSRF protection: forbid localhost, private, or metadata IPs
        url_lower = self.target_url.lower()
        forbidden_hosts = ['localhost', '127.0.0.1', '0.0.0.0', '169.254.169.254', '10.', '192.168.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.3']
        for fh in forbidden_hosts:
            if f"://{fh}" in url_lower or f"@{fh}" in url_lower:
                raise ValidationError("Internal network or private IP destinations are forbidden for webhooks.")


class WebhookDeliveryLog(models.Model):
    """
    Log and durable dispatch state for webhook deliveries with retries, status codes, and payload digests.
    """
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='delivery_logs')
    event_type = models.CharField(max_length=60)
    event_id = models.CharField(max_length=64, blank=True, db_index=True)
    delivery_id = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True)
    state = models.CharField(
        max_length=20,
        default='PENDING',
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('DELIVERED', 'Delivered'),
            ('FAILED', 'Failed'),
            ('DEAD_LETTER', 'Dead Letter'),
        ],
        db_index=True
    )
    payload_digest = models.CharField(max_length=64, help_text="SHA256 digest of payload for auditing without disclosing sensitive customer text")
    payload_data = models.JSONField(default=dict, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claim_token = models.CharField(max_length=64, blank=True, default='')
    is_success = models.BooleanField(default=False)
    response_body = models.TextField(blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['state', 'next_attempt_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['endpoint', 'event_id'],
                name='unique_endpoint_event_delivery',
                condition=models.Q(event_id__gt='')
            )
        ]


class TenantIntegration(models.Model):
    """
    Connector registry for external services (Calendar, external CRM, accounting).
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='integrations')
    integration_type = models.CharField(
        max_length=40,
        choices=[
            ('CALENDAR', 'Calendar Sync'),
            ('CRM_CONNECTOR', 'External CRM Sync'),
            ('COMMERCE', 'E-Commerce / Order Sync'),
            ('CUSTOM_WEBHOOK', 'Custom Webhooks'),
        ]
    )
    name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        default='UNCONFIGURED',
        choices=[
            ('UNCONFIGURED', 'Unconfigured'),
            ('CONFIGURED', 'Configured (Awaiting Sync)'),
            ('ACTIVE', 'Active & Connected'),
            ('ERROR', 'Configuration Error'),
        ]
    )
    config = models.JSONField(default=dict)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'integration_type', 'name')

