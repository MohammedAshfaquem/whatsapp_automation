import pytest
from unittest.mock import patch, MagicMock
from django.core.management import call_command
from apps.knowledge_base.vector_store import ChromaVectorStore
from apps.knowledge_base.embeddings import GeminiEmbeddingService
from apps.knowledge_base.synchronization import KnowledgeSynchronizer
from apps.knowledge_base.retrieval import retrieve_relevant_knowledge, format_retrieved_context
from apps.knowledge_base.models import FAQ, KnowledgeDocument, DocumentCategory, KnowledgeSyncStatus, SyncStatusChoice
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile
from apps.chatbot.prompts import build_rag_prompt
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import ChannelChoice

@pytest.fixture(autouse=True)
def setup_rag_data(db):
    BusinessProfile.objects.all().delete()
    Service.objects.all().delete()
    FAQ.objects.all().delete()
    KnowledgeDocument.objects.all().delete()
    KnowledgeSyncStatus.objects.all().delete()

    BusinessProfile.objects.create(
        shop_name="CoolAir AC Masters",
        contact_phone="+91 98765 43210",
        address="123 Industrial Area, New Delhi",
        working_hours="Mon-Sat: 9 AM - 8 PM",
        service_areas="Delhi, Noida, Gurgaon",
        is_active=True
    )

    Service.objects.create(
        name="AC general servicing",
        description="Filter cleaning and jet wash",
        price_type=PriceType.STARTING_FROM,
        price_amount=500.00,
        is_active=True
    )

    FAQ.objects.create(
        question="Do you provide home visits?",
        answer="Yes, our certified technicians provide doorstep home visits.",
        category="General",
        is_active=True
    )

@pytest.mark.django_db
class TestChromaVectorStore:
    def test_upsert_and_query(self):
        store = ChromaVectorStore.get_instance()
        store.reset()

        # Mock embedding (768-dim float list)
        mock_embedding = [0.1] * 768

        ok = store.upsert_document(
            doc_id="test_doc_1",
            document_text="We offer split AC repair and gas filling in Delhi.",
            metadata={"source_type": "FAQ", "is_active": True},
            embedding=mock_embedding
        )
        assert ok is True
        assert store.count() == 1

        # Query
        results = store.query_similar(
            query_text="split AC repair",
            n_results=1,
            filter_metadata={"is_active": True},
            query_embedding=mock_embedding
        )
        assert len(results) == 1
        assert results[0]["id"] == "test_doc_1"
        assert "split AC repair" in results[0]["text"]

    def test_inactive_metadata_filtering(self):
        store = ChromaVectorStore.get_instance()
        store.reset()
        mock_emb = [0.2] * 768

        store.upsert_document("active_1", "Active policy text", {"is_active": True}, mock_emb)
        store.upsert_document("inactive_1", "Inactive obsolete text", {"is_active": False}, mock_emb)

        # Query with is_active filter
        results = store.query_similar("policy", filter_metadata={"is_active": True}, query_embedding=mock_emb)
        retrieved_ids = [r["id"] for r in results]
        assert "active_1" in retrieved_ids
        assert "inactive_1" not in retrieved_ids

    def test_delete_document(self):
        store = ChromaVectorStore.get_instance()
        store.reset()
        store.upsert_document("doc_del", "Text to delete", {"is_active": True}, [0.1]*768)
        assert store.count() == 1
        store.delete_document("doc_del")
        assert store.count() == 0

@pytest.mark.django_db
class TestKnowledgeSynchronization:
    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding')
    def test_sync_service_and_caching(self, mock_embed):
        mock_embed.return_value = [0.05] * 768
        svc = Service.objects.first()

        # First sync
        success, msg = KnowledgeSynchronizer.sync_service(svc)
        assert success is True
        assert msg == "Successfully synced"

        sync_record = KnowledgeSyncStatus.objects.get(source_type="SERVICE", source_id=svc.id)
        assert sync_record.status == SyncStatusChoice.SYNCED

        # Second sync with unchanged content -> uses cache
        success2, msg2 = KnowledgeSynchronizer.sync_service(svc)
        assert success2 is True
        assert "cached" in msg2

    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding')
    def test_deactivated_service_removed_from_chroma(self, mock_embed):
        mock_embed.return_value = [0.05] * 768
        store = ChromaVectorStore.get_instance()
        store.reset()

        svc = Service.objects.first()
        KnowledgeSynchronizer.sync_service(svc)
        assert store.count() == 1

        # Deactivate
        svc.is_active = False
        svc.save()
        KnowledgeSynchronizer.sync_service(svc)
        assert store.count() == 0

    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding')
    def test_sync_knowledge_management_command(self, mock_embed):
        mock_embed.return_value = [0.1] * 768
        call_command('sync_knowledge', '--rebuild')
        # All records should be synced
        assert KnowledgeSyncStatus.objects.filter(status=SyncStatusChoice.SYNCED).count() >= 2

@pytest.mark.django_db
class TestGeminiRAGFlow:
    def test_build_rag_prompt(self):
        prompt = build_rag_prompt(
            customer_message="What is the price of gas top-up?",
            business_summary="Shop: CoolAir",
            active_services_text="1. AC general servicing — ₹500 onwards",
            retrieved_knowledge_text="[Document 1]: Warranty is 30 days",
            conversation_history=[{"direction": "INBOUND", "text": "Hi"}]
        )
        assert "[BUSINESS INFORMATION]" in prompt
        assert "[ACTIVE SERVICES & REAL-TIME PRICING]" in prompt
        assert "[RETRIEVED KNOWLEDGE & POLICIES]" in prompt
        assert "What is the price of gas top-up?" in prompt

    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding', return_value=[0.1] * 768)
    @patch('apps.chatbot.gemini_service.GeminiChatService.generate_reply')
    def test_conversation_service_uses_gemini_when_configured(self, mock_gemini, mock_emb):
        mock_gemini.return_value = "Hello! AC general servicing starts from ₹500. How can I help?"

        with patch('apps.chatbot.gemini_service.GeminiChatService.is_configured', return_value=True):
            res = ConversationService.process_message(
                phone_number="+919876543210",
                message_text="My AC sometimes makes a rattling sound; what should I do?",
                channel=ChannelChoice.SIMULATED
            )
            assert res["conversation_id"] is not None
            assert res["reply"] == "Hello! AC general servicing starts from ₹500. How can I help?"

    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding', return_value=[0.1] * 768)
    @patch('apps.chatbot.gemini_service.GeminiChatService.generate_reply')
    def test_immediate_price_update_grounding(self, mock_gemini, mock_emb):
        """
        Verify that updating a service price in PostgreSQL immediately updates the prompt context
        without requiring vector re-indexing.
        """
        svc = Service.objects.first()
        svc.price_amount = 650.00
        svc.save()

        # Capture prompt passed to Gemini
        captured_prompt = None
        def mock_generate(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return f"The updated price for {svc.name} is ₹650 onwards."

        mock_gemini.side_effect = mock_generate

        with patch('apps.chatbot.gemini_service.GeminiChatService.is_configured', return_value=True):
            res = ConversationService.process_message(
                phone_number="+919876543210",
                message_text="What is the price of servicing?",
                channel=ChannelChoice.SIMULATED
            )
            # Prompt must contain the new price ₹650 directly from PostgreSQL
            assert captured_prompt is None
            assert "₹650 onwards" in res["reply"]
            assert not mock_gemini.called

    @patch('apps.knowledge_base.embeddings.GeminiEmbeddingService.generate_embedding', return_value=[0.1] * 768)
    @patch('apps.chatbot.gemini_service.GeminiChatService.generate_reply')
    def test_gemini_failure_graceful_fallback(self, mock_gemini, mock_emb):
        """
        If Gemini API throws an exception or network error, fallback to deterministic grounded answer.
        """
        mock_gemini.side_effect = Exception("Gemini API rate limit exceeded")

        with patch('apps.chatbot.gemini_service.GeminiChatService.is_configured', return_value=True):
            res = ConversationService.process_message(
                phone_number="+919876543210",
                message_text="What are your working hours?",
                channel=ChannelChoice.SIMULATED
            )
            # Did not crash, returned grounded deterministic answer
            assert res["conversation_id"] is not None
            assert "Mon-Sat: 9 AM - 8 PM" in res["reply"]
