import hashlib
import logging
from typing import Dict, Any, Tuple
from django.utils import timezone
from apps.services.models import Service
from apps.business.models import BusinessProfile
from apps.knowledge_base.models import (
    FAQ,
    KnowledgeDocument,
    KnowledgeSyncStatus,
    SourceTypeChoice,
    SyncStatusChoice
)
from .vector_store import ChromaVectorStore
from .embeddings import GeminiEmbeddingService

logger = logging.getLogger(__name__)

def compute_hash(text: str) -> str:
    """Generate SHA-256 hash of text content."""
    return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()

class KnowledgeSynchronizer:
    """
    Synchronizes PostgreSQL services, FAQs, and business policies with ChromaDB.
    Maintains synchronization state in KnowledgeSyncStatus to prevent drift.
    """

    @classmethod
    def sync_service(cls, service: Service) -> Tuple[bool, str]:
        """Synchronize an AC Service to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        doc_id = f"service_{service.id}"

        # If deactivated, remove from vector store immediately
        if not service.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                source_type=SourceTypeChoice.SERVICE,
                source_id=service.id,
                defaults={
                    "vector_id": doc_id,
                    "status": SyncStatusChoice.SYNCED,
                    "last_error": "Deactivated - vector removed",
                    "last_synced_at": timezone.now()
                }
            )
            return True, "Deactivated vector removed"

        # Build representation (Note: description + category; prices are retrieved from PostgreSQL directly)
        text_content = (
            f"Service: {service.name}\n"
            f"Category: {service.category}\n"
            f"Pricing Type: {service.get_price_type_display()}\n"
            f"Current Price: {service.formatted_price}\n"
            f"Duration: {service.estimated_duration}\n"
            f"Description: {service.description}"
        )
        content_hash = compute_hash(text_content)

        metadata = {
            "source_type": SourceTypeChoice.SERVICE,
            "source_id": service.id,
            "name": service.name,
            "category": service.category,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.SERVICE,
            source_id=service.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata
        )

    @classmethod
    def sync_faq(cls, faq: FAQ) -> Tuple[bool, str]:
        """Synchronize a FAQ to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        doc_id = f"faq_{faq.id}"

        if not faq.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                source_type=SourceTypeChoice.FAQ,
                source_id=faq.id,
                defaults={
                    "vector_id": doc_id,
                    "status": SyncStatusChoice.SYNCED,
                    "last_error": "Deactivated - vector removed",
                    "last_synced_at": timezone.now()
                }
            )
            return True, "Deactivated FAQ vector removed"

        text_content = f"Question: {faq.question}\nAnswer: {faq.answer}\nCategory: {faq.category}"
        content_hash = compute_hash(text_content)

        metadata = {
            "source_type": SourceTypeChoice.FAQ,
            "source_id": faq.id,
            "question": faq.question,
            "category": faq.category,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.FAQ,
            source_id=faq.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata
        )

    @classmethod
    def sync_document(cls, doc: KnowledgeDocument) -> Tuple[bool, str]:
        """Synchronize a KnowledgeDocument policy or guide to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        doc_id = f"doc_{doc.id}"

        if not doc.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                source_type=SourceTypeChoice.DOCUMENT,
                source_id=doc.id,
                defaults={
                    "vector_id": doc_id,
                    "status": SyncStatusChoice.SYNCED,
                    "last_error": "Deactivated - vector removed",
                    "last_synced_at": timezone.now()
                }
            )
            return True, "Deactivated doc vector removed"

        text_content = f"Title: {doc.title}\nCategory: {doc.get_category_display()}\nContent: {doc.content}"
        content_hash = compute_hash(text_content)

        metadata = {
            "source_type": SourceTypeChoice.DOCUMENT,
            "source_id": doc.id,
            "title": doc.title,
            "category": doc.category,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.DOCUMENT,
            source_id=doc.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata
        )

    @classmethod
    def sync_business_profile(cls, profile: BusinessProfile) -> Tuple[bool, str]:
        """Synchronize BusinessProfile to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        doc_id = f"business_{profile.id}"

        if not profile.is_active:
            vector_store.delete_document(doc_id)
            return True, "Deactivated profile vector removed"

        text_content = (
            f"Business: {profile.shop_name}\n"
            f"Phone: {profile.contact_phone}\n"
            f"Address: {profile.address}\n"
            f"Hours: {profile.working_hours}\n"
            f"Holidays: {profile.holiday_information}\n"
            f"Service Areas: {profile.service_areas}\n"
            f"Supported ACs: {profile.supported_ac_types}\n"
            f"Brands: {profile.supported_ac_brands}\n"
            f"Warranty: {profile.warranty_policies}\n"
            f"Payments: {profile.accepted_payment_methods}\n"
            f"Policies: {profile.general_service_policies}"
        )
        content_hash = compute_hash(text_content)
        metadata = {
            "source_type": SourceTypeChoice.BUSINESS,
            "source_id": profile.id,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.BUSINESS,
            source_id=profile.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata
        )

    @classmethod
    def _upsert_and_record(
        cls,
        source_type: str,
        source_id: int,
        doc_id: str,
        text_content: str,
        content_hash: str,
        metadata: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Check existing sync record; if content unchanged and already synced, skip re-embedding.
        Otherwise generate embedding and upsert to ChromaDB.
        """
        existing_sync = KnowledgeSyncStatus.objects.filter(
            source_type=source_type,
            source_id=source_id
        ).first()

        if existing_sync and existing_sync.status == SyncStatusChoice.SYNCED and existing_sync.content_hash == content_hash:
            return True, "Content unchanged (cached)"

        vector_store = ChromaVectorStore.get_instance()
        embedding = GeminiEmbeddingService.generate_embedding(text_content)

        success = vector_store.upsert_document(
            doc_id=doc_id,
            document_text=text_content,
            metadata=metadata,
            embedding=embedding
        )

        status_val = SyncStatusChoice.SYNCED if success else SyncStatusChoice.FAILED
        err_msg = "" if success else "Failed to upsert to ChromaDB"

        KnowledgeSyncStatus.objects.update_or_create(
            source_type=source_type,
            source_id=source_id,
            defaults={
                "vector_id": doc_id,
                "content_hash": content_hash,
                "status": status_val,
                "last_error": err_msg,
                "last_synced_at": timezone.now() if success else None
            }
        )

        return success, "Successfully synced" if success else err_msg

    @classmethod
    def sync_all(cls) -> Dict[str, int]:
        """
        Synchronize all active records across Services, FAQs, KnowledgeDocuments, and BusinessProfile.
        """
        stats = {"services": 0, "faqs": 0, "documents": 0, "business": 0, "errors": 0}

        for svc in Service.objects.all():
            ok, _ = cls.sync_service(svc)
            if ok:
                stats["services"] += 1
            else:
                stats["errors"] += 1

        for faq in FAQ.objects.all():
            ok, _ = cls.sync_faq(faq)
            if ok:
                stats["faqs"] += 1
            else:
                stats["errors"] += 1

        for doc in KnowledgeDocument.objects.all():
            ok, _ = cls.sync_document(doc)
            if ok:
                stats["documents"] += 1
            else:
                stats["errors"] += 1

        active_profile = BusinessProfile.get_active()
        if active_profile:
            ok, _ = cls.sync_business_profile(active_profile)
            if ok:
                stats["business"] += 1
            else:
                stats["errors"] += 1

        return stats
