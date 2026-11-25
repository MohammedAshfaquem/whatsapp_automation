import logging
from typing import List, Dict, Any
from .vector_store import ChromaVectorStore
from .embeddings import GeminiEmbeddingService

logger = logging.getLogger(__name__)

def retrieve_relevant_knowledge(
    query_text: str,
    n_results: int = 4,
    min_score: float = 0.25,
    tenant=None
) -> List[Dict[str, Any]]:
    """
    Retrieve semantically similar knowledge chunks from ChromaDB.
    Filters out inactive records and chunks with low similarity scores,
    enforcing strict tenant isolation.
    """
    if not query_text or not query_text.strip():
        return []

    from apps.tenants.context import get_current_tenant
    if tenant is None:
        tenant = get_current_tenant()

    vector_store = ChromaVectorStore.get_instance()
    if not vector_store.is_available:
        return []

    # Generate query embedding
    query_embedding = GeminiEmbeddingService.generate_embedding(query_text)

    # Query ChromaDB with active and tenant filter
    if tenant and tenant.id:
        filter_metadata = {"$and": [{"is_active": True}, {"tenant_id": tenant.id}]}
    else:
        filter_metadata = {"is_active": True}

    results = vector_store.query_similar(
        query_text=query_text,
        n_results=n_results,
        filter_metadata=filter_metadata,
        query_embedding=query_embedding
    )

    # Filter by minimum similarity score if distances are reliable
    filtered = []
    for chunk in results:
        # Extra safety check: verify chunk metadata matches tenant
        if tenant and tenant.id:
            chunk_tenant_id = chunk.get("metadata", {}).get("tenant_id")
            if chunk_tenant_id is not None and chunk_tenant_id != tenant.id:
                continue
        if 1.0 - chunk.get("distance", 1.0) >= min_score:
            filtered.append(chunk)

    return filtered

def format_retrieved_context(chunks: List[Dict[str, Any]]) -> str:
    """
    Format retrieved knowledge chunks into concise text blocks for LLM prompt context.
    """
    if not chunks:
        return "No specific FAQ or policy document matched."

    formatted = []
    for idx, c in enumerate(chunks, 1):
        text = c.get("text", "").strip()
        formatted.append(f"[Document {idx}]:\n{text}")

    return "\n\n".join(formatted)
