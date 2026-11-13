import pytest
from apps.knowledge_base.models import (
    FAQ,
    KnowledgeDocument,
    DocumentCategory,
    KnowledgeSyncStatus,
    SourceTypeChoice,
    SyncStatusChoice
)

@pytest.mark.django_db
class TestKnowledgeBaseModels:
    def test_faq_creation(self):
        faq = FAQ.objects.create(
            question="Do you fix cassette ACs?",
            answer="Yes, our commercial technicians specialize in cassette AC repairs.",
            category="Commercial"
        )
        assert str(faq) == "Do you fix cassette ACs?"
        assert faq.is_active is True

    def test_knowledge_document_slug_auto_generation(self):
        doc = KnowledgeDocument.objects.create(
            title="Monsoon AC Care Tips",
            category=DocumentCategory.TROUBLESHOOTING,
            content="Keep outer units dry and clear from mud."
        )
        assert doc.slug == "monsoon-ac-care-tips"
        assert doc.get_category_display() == "Troubleshooting Guidance"

    def test_knowledge_sync_status(self):
        sync = KnowledgeSyncStatus.objects.create(
            source_type=SourceTypeChoice.SERVICE,
            source_id=1,
            vector_id="service_1",
            content_hash="abc123hash",
            status=SyncStatusChoice.PENDING
        )
        assert sync.status == SyncStatusChoice.PENDING
        assert "SERVICE #1" in str(sync)
