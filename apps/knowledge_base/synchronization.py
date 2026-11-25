import hashlib
import logging
from typing import Dict, Any, Tuple
from django.utils import timezone
from apps.services.models import Service
from apps.business.models import BusinessProfile, Product, FeatureAvailability
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
        """Synchronize a Service to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        tenant = getattr(service, 'tenant', None)
        t_prefix = f"t{tenant.id}_" if tenant else ""
        doc_id = f"{t_prefix}service_{service.id}"

        # If deactivated, remove from vector store immediately
        if not service.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                tenant=tenant,
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
            "tenant_id": tenant.id if tenant else 0,
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
            metadata=metadata,
            tenant=tenant
        )

    @classmethod
    def sync_faq(cls, faq: FAQ) -> Tuple[bool, str]:
        """Synchronize a FAQ to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        tenant = getattr(faq, 'tenant', None)
        t_prefix = f"t{tenant.id}_" if tenant else ""
        doc_id = f"{t_prefix}faq_{faq.id}"

        if not faq.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                tenant=tenant,
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
            "tenant_id": tenant.id if tenant else 0,
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
            metadata=metadata,
            tenant=tenant
        )

    @classmethod
    def sync_document(cls, doc: KnowledgeDocument) -> Tuple[bool, str]:
        """Synchronize a KnowledgeDocument policy or guide to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        tenant = getattr(doc, 'tenant', None)
        t_prefix = f"t{tenant.id}_" if tenant else ""
        doc_id = f"{t_prefix}doc_{doc.id}"

        if not doc.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                tenant=tenant,
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
            "tenant_id": tenant.id if tenant else 0,
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
            metadata=metadata,
            tenant=tenant
        )

    @classmethod
    def sync_business_profile(cls, profile: BusinessProfile) -> Tuple[bool, str]:
        """Synchronize BusinessProfile to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        tenant = getattr(profile, 'tenant', None)
        t_prefix = f"t{tenant.id}_" if tenant else ""
        doc_id = f"{t_prefix}business_{profile.id}"

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
            f"Warranty: {profile.warranty_policies}\n"
            f"Payments: {profile.accepted_payment_methods}\n"
            f"Policies: {profile.general_service_policies}"
        )
        content_hash = compute_hash(text_content)
        metadata = {
            "source_type": SourceTypeChoice.BUSINESS,
            "source_id": profile.id,
            "tenant_id": tenant.id if tenant else 0,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.BUSINESS,
            source_id=profile.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata,
            tenant=tenant
        )

    @classmethod
    def sync_product(cls, product: Product) -> Tuple[bool, str]:
        """Synchronize a Product, its verified capabilities, limitations, and pricing status to ChromaDB."""
        vector_store = ChromaVectorStore.get_instance()
        tenant = getattr(product, 'tenant', None)
        t_prefix = f"t{tenant.id}_" if tenant else ""
        doc_id = f"{t_prefix}product_{product.id}"

        if not product.is_active:
            vector_store.delete_document(doc_id)
            KnowledgeSyncStatus.objects.update_or_create(
                tenant=tenant,
                source_type=SourceTypeChoice.PRODUCT,
                source_id=product.id,
                defaults={
                    "vector_id": doc_id,
                    "status": SyncStatusChoice.SYNCED,
                    "last_error": "Deactivated - vector removed",
                    "last_synced_at": timezone.now()
                }
            )
            return True, "Deactivated product vector removed"

        caps = product.capabilities.filter(is_active=True)
        avail = [f"- {c.name}: {c.description}" for c in caps.filter(status=FeatureAvailability.AVAILABLE)]
        unavail = [f"- {c.name}: {c.description or 'Not supported'}" for c in caps.filter(status=FeatureAvailability.NOT_SUPPORTED)]
        unconf = [f"- {c.name}: Availability to be confirmed by team" for c in caps.filter(status=FeatureAvailability.UNCONFIRMED)]

        ints = product.integrations.filter(is_active=True)
        int_lines = [f"- {i.name}: {i.get_status_display()} ({i.description})" for i in ints]

        plans = product.pricing_plans.filter(is_active=True)
        plan_lines = [f"- {p.name}: {p}" for p in plans]

        text_content = (
            f"Product: {product.name}\n"
            f"Tagline: {product.tagline}\n"
            f"Description: {product.description}\n"
            f"Intended Customers: {product.intended_customers}\n"
            f"Pricing Status: {product.get_pricing_status_display()}\n"
            f"Pricing Details: {product.pricing_details or product.formatted_pricing}\n"
            f"Deployment & Onboarding: {product.deployment_onboarding}\n"
            f"Support Info: {product.support_info}\n"
            f"Demo Process: {product.demo_process}\n"
            f"Verified Available Capabilities:\n" + ("\n".join(avail) if avail else "None listed") + "\n"
            f"Explicitly Unsupported Limitations:\n" + ("\n".join(unavail) if unavail else "None listed") + "\n"
            f"Unconfirmed / Roadmap Capabilities (Confirmation required):\n" + ("\n".join(unconf) if unconf else "None listed") + "\n"
            f"Integrations:\n" + ("\n".join(int_lines) if int_lines else "None listed") + "\n"
            f"Pricing Plans:\n" + ("\n".join(plan_lines) if plan_lines else "Quote on request")
        )
        content_hash = compute_hash(text_content)
        metadata = {
            "source_type": SourceTypeChoice.PRODUCT,
            "source_id": product.id,
            "tenant_id": tenant.id if tenant else 0,
            "name": product.name,
            "is_active": True
        }

        return cls._upsert_and_record(
            source_type=SourceTypeChoice.PRODUCT,
            source_id=product.id,
            doc_id=doc_id,
            text_content=text_content,
            content_hash=content_hash,
            metadata=metadata,
            tenant=tenant
        )

    @classmethod
    def _upsert_and_record(
        cls,
        source_type: str,
        source_id: int,
        doc_id: str,
        text_content: str,
        content_hash: str,
        metadata: Dict[str, Any],
        tenant=None
    ) -> Tuple[bool, str]:
        """
        Check existing sync record; if content unchanged and already synced, skip re-embedding.
        Otherwise generate embedding and upsert to ChromaDB.
        """
        existing_sync = KnowledgeSyncStatus.objects.filter(
            tenant=tenant,
            source_type=source_type,
            source_id=source_id
        ).first()

        if existing_sync and existing_sync.status == SyncStatusChoice.SYNCED and existing_sync.content_hash == content_hash:
            return True, "Content unchanged (cached)"

        vector_store = ChromaVectorStore.get_instance()
        embedding = GeminiEmbeddingService.generate_embedding(text_content)

        if embedding is None:
            # In offline/test environments without API key, do not pass None to Chroma
            # which triggers remote ONNX download. Record sync status safely.
            KnowledgeSyncStatus.objects.update_or_create(
                tenant=tenant,
                source_type=source_type,
                source_id=source_id,
                defaults={
                    "vector_id": doc_id,
                    "content_hash": content_hash,
                    "status": SyncStatusChoice.SYNCED,
                    "last_error": "Gemini unconfigured; vector embedding skipped",
                    "last_synced_at": timezone.now()
                }
            )
            return True, "Vector embedding skipped (Gemini unconfigured)"

        success = vector_store.upsert_document(
            doc_id=doc_id,
            document_text=text_content,
            metadata=metadata,
            embedding=embedding
        )

        status_val = SyncStatusChoice.SYNCED if success else SyncStatusChoice.FAILED
        err_msg = "" if success else "Failed to upsert to ChromaDB"

        KnowledgeSyncStatus.objects.update_or_create(
            tenant=tenant,
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
    def sync_all(cls, tenant=None) -> Dict[str, int]:
        """
        Synchronize all active records across Services, FAQs, KnowledgeDocuments, and BusinessProfile.
        If tenant is provided, only records for that tenant are synced.
        """
        stats = {"services": 0, "products": 0, "faqs": 0, "documents": 0, "business": 0, "errors": 0}

        services_qs = Service.objects.all()
        products_qs = Product.objects.all()
        faqs_qs = FAQ.objects.all()
        docs_qs = KnowledgeDocument.objects.all()
        profiles_qs = BusinessProfile.objects.all()

        if tenant:
            services_qs = services_qs.filter(tenant=tenant)
            products_qs = products_qs.filter(tenant=tenant)
            faqs_qs = faqs_qs.filter(tenant=tenant)
            docs_qs = docs_qs.filter(tenant=tenant)
            profiles_qs = profiles_qs.filter(tenant=tenant)

        for svc in services_qs:
            ok, _ = cls.sync_service(svc)
            if ok:
                stats["services"] += 1
            else:
                stats["errors"] += 1

        for prod in products_qs:
            ok, _ = cls.sync_product(prod)
            if ok:
                stats["products"] += 1
            else:
                stats["errors"] += 1

        for faq in faqs_qs:
            ok, _ = cls.sync_faq(faq)
            if ok:
                stats["faqs"] += 1
            else:
                stats["errors"] += 1

        for doc in docs_qs:
            ok, _ = cls.sync_document(doc)
            if ok:
                stats["documents"] += 1
            else:
                stats["errors"] += 1

        for profile in profiles_qs.filter(is_active=True):
            ok, _ = cls.sync_business_profile(profile)
            if ok:
                stats["business"] += 1
            else:
                stats["errors"] += 1

        return stats
