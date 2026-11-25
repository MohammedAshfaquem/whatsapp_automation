from django.db import models
from django.utils.text import slugify

class FAQ(models.Model):
    """
    Frequently Asked Questions managed by shop owner.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='faqs', null=True, blank=True)
    question = models.CharField(max_length=255, help_text="e.g. Do you provide software development services?")
    answer = models.TextField(help_text="Clear, customer-friendly answer")
    category = models.CharField(max_length=100, default="General", help_text="e.g. Services, Timings, Coverage, Booking")
    is_active = models.BooleanField(default=True, help_text="Whether this FAQ is used by AI for retrieval")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'id']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"
        unique_together = ('tenant', 'question')

    def __str__(self):
        return self.question

class DocumentCategory(models.TextChoices):
    POLICY = 'POLICY', 'Service Policy'
    WARRANTY = 'WARRANTY', 'Warranty Details'
    TROUBLESHOOTING = 'TROUBLESHOOTING', 'Troubleshooting Guidance'
    TERMS = 'TERMS', 'Terms and Conditions'
    OTHER = 'OTHER', 'Other Information'

class KnowledgeDocument(models.Model):
    """
    Shop documents, policies, warranties, and troubleshooting guides for RAG ingestion.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    category = models.CharField(max_length=40, choices=DocumentCategory.choices, default=DocumentCategory.POLICY)
    content = models.TextField(help_text="Detailed text content ingested into the vector store")
    is_active = models.BooleanField(default=True, help_text="Exclude inactive documents from RAG retrieval")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'title']
        verbose_name = "Knowledge Document"
        verbose_name_plural = "Knowledge Documents"
        unique_together = (('tenant', 'title'), ('tenant', 'slug'))

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    def clean(self):
        super().clean()
        if self.tenant and not self.pk and not self.tenant.can_add_document():
            from django.core.exceptions import ValidationError
            raise ValidationError(f"Document limit reached ({self.tenant.effective_max_documents} documents) for current plan.")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

class SyncStatusChoice(models.TextChoices):
    PENDING = 'PENDING', 'Pending Sync'
    SYNCED = 'SYNCED', 'Synced to Vector Store'
    FAILED = 'FAILED', 'Sync Failed'

class SourceTypeChoice(models.TextChoices):
    SERVICE = 'SERVICE', 'Service'
    FAQ = 'FAQ', 'FAQ'
    DOCUMENT = 'DOCUMENT', 'Knowledge Document'
    BUSINESS = 'BUSINESS', 'Business Profile'
    PRODUCT = 'PRODUCT', 'Product'

class KnowledgeSyncStatus(models.Model):
    """
    Tracks vector database synchronization state for each database record.
    Prevents PostgreSQL and ChromaDB drift.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='sync_statuses', null=True, blank=True)
    source_type = models.CharField(max_length=30, choices=SourceTypeChoice.choices)
    source_id = models.PositiveIntegerField(help_text="Primary key of source record in PostgreSQL")
    vector_id = models.CharField(max_length=150, blank=True, help_text="Deterministic ID used in ChromaDB")
    content_hash = models.CharField(max_length=64, blank=True, help_text="SHA-256 hash of content")
    status = models.CharField(max_length=20, choices=SyncStatusChoice.choices, default=SyncStatusChoice.PENDING)
    last_error = models.TextField(blank=True, help_text="Error message if sync failed")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Knowledge Sync Status"
        verbose_name_plural = "Knowledge Sync Statuses"
        unique_together = ('tenant', 'source_type', 'source_id')
        indexes = [
            models.Index(fields=['tenant', 'source_type', 'source_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.source_type} #{self.source_id} - {self.status}"
