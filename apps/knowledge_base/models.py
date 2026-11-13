from django.db import models
from django.utils.text import slugify

class FAQ(models.Model):
    """
    Frequently Asked Questions managed by shop owner.
    """
    question = models.CharField(max_length=255, unique=True, help_text="e.g. Do you provide split AC repair?")
    answer = models.TextField(help_text="Clear, customer-friendly answer")
    category = models.CharField(max_length=100, default="General", help_text="e.g. Services, Timings, Coverage, Booking")
    is_active = models.BooleanField(default=True, help_text="Whether this FAQ is used by AI for retrieval")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'id']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

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
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=40, choices=DocumentCategory.choices, default=DocumentCategory.POLICY)
    content = models.TextField(help_text="Detailed text content ingested into the vector store")
    is_active = models.BooleanField(default=True, help_text="Exclude inactive documents from RAG retrieval")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'title']
        verbose_name = "Knowledge Document"
        verbose_name_plural = "Knowledge Documents"

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

class SyncStatusChoice(models.TextChoices):
    PENDING = 'PENDING', 'Pending Sync'
    SYNCED = 'SYNCED', 'Synced to Vector Store'
    FAILED = 'FAILED', 'Sync Failed'

class SourceTypeChoice(models.TextChoices):
    SERVICE = 'SERVICE', 'AC Service'
    FAQ = 'FAQ', 'FAQ'
    DOCUMENT = 'DOCUMENT', 'Knowledge Document'
    BUSINESS = 'BUSINESS', 'Business Profile'

class KnowledgeSyncStatus(models.Model):
    """
    Tracks vector database synchronization state for each database record.
    Prevents PostgreSQL and ChromaDB drift.
    """
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
        unique_together = ('source_type', 'source_id')
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.source_type} #{self.source_id} - {self.status}"
