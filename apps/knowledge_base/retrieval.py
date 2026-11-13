import logging
from typing import List, Dict, Any
from .vector_store import ChromaVectorStore
from .embeddings import GeminiEmbeddingService

logger = logging.getLogger(__name__)

def retrieve_relevant_knowledge(
    query_text: str,
    n_results: int = 4,
    min_score: float = 0.25
) -> List[Dict[str, Any]]:
    """
    Retrieve semantically similar knowledge chunks from ChromaDB.
    Filters out inactive records and chunks with low similarity scores.
    """
    if not query_text or not query_text.strip():
        return []

    vector_store = ChromaVectorStore.get_instance()
    if not vector_store.is_available:
        return []

    # Generate query embedding
    query_embedding = GeminiEmbeddingService.generate_embedding(query_text)

    # Query ChromaDB with active filter
    results = vector_store.query_similar(
        query_text=query_text,
        n_results=n_results,
        filter_metadata={"is_active": True},
        query_embedding=query_embedding
    )

    # Filter by minimum similarity score if distances are reliable
    filtered = []
    for chunk in results:
        # Distance <= 0.8 roughly corresponds to score >= 0.2 in cosine space
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
