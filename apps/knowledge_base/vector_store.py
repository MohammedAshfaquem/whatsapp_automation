import logging
from typing import List, Dict, Any, Optional
from django.conf import settings
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    ChromaDB persistent vector store wrapper for semantic retrieval of
    shop FAQs, service descriptions, and business policies.
    """
    _instance: Optional['ChromaVectorStore'] = None
    _client: Optional[chromadb.PersistentClient] = None
    _collection: Optional[chromadb.Collection] = None

    def __init__(self):
        persist_dir = getattr(settings, 'CHROMA_PERSIST_DIRECTORY', './chroma_data')
        collection_name = getattr(settings, 'CHROMA_COLLECTION_NAME', 'ac_shop_knowledge')

        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Initialized ChromaDB at {persist_dir} with collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            self._client = None
            self._collection = None

    @classmethod
    def get_instance(cls) -> 'ChromaVectorStore':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def upsert_document(
        self,
        doc_id: str,
        document_text: str,
        metadata: Dict[str, Any],
        embedding: Optional[List[float]] = None
    ) -> bool:
        """
        Upsert a text chunk with metadata into ChromaDB using deterministic document ID.
        """
        if not self.is_available:
            logger.warning("ChromaDB collection is unavailable. Skipping upsert.")
            return False

        try:
            kwargs = {
                "ids": [doc_id],
                "documents": [document_text],
                "metadatas": [metadata]
            }
            if embedding is not None and len(embedding) > 0:
                kwargs["embeddings"] = [embedding]

            self._collection.upsert(**kwargs)
            return True
        except Exception as e:
            logger.error(f"Error upserting document {doc_id} to ChromaDB: {e}", exc_info=True)
            return False

    def query_similar(
        self,
        query_text: str,
        n_results: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        query_embedding: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query ChromaDB for semantically similar documents, applying metadata filters.
        """
        if not self.is_available:
            logger.warning("ChromaDB is unavailable. Returning empty retrieval list.")
            return []

        try:
            total_docs = self.count()
            if total_docs == 0:
                return []

            actual_n = min(n_results, total_docs)
            kwargs = {
                "n_results": actual_n,
            }
            if filter_metadata:
                kwargs["where"] = filter_metadata

            if query_embedding is not None and len(query_embedding) > 0:
                kwargs["query_embeddings"] = [query_embedding]
            else:
                # If Gemini embedding is unavailable and collection has 768 dimensions,
                # querying with query_texts would trigger Chroma's default 384-dim embedder and raise an error.
                # Gracefully skip vector retrieval.
                logger.warning("Query embedding is not available. Skipping ChromaDB vector search.")
                return []

            results = self._collection.query(**kwargs)

            retrieved = []
            if results and results.get("ids") and len(results["ids"]) > 0:
                ids = results["ids"][0]
                docs = results["documents"][0] if results.get("documents") else []
                metas = results["metadatas"][0] if results.get("metadatas") else []
                distances = results["distances"][0] if results.get("distances") else []

                for idx, doc_id in enumerate(ids):
                    doc_content = docs[idx] if idx < len(docs) else ""
                    meta = metas[idx] if idx < len(metas) else {}
                    dist = distances[idx] if idx < len(distances) else 1.0
                    score = 1.0 - dist  # Cosine similarity approximation

                    retrieved.append({
                        "id": doc_id,
                        "text": doc_content,
                        "metadata": meta,
                        "distance": dist,
                        "score": round(score, 4)
                    })

            return retrieved
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}", exc_info=True)
            return []

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document vector by ID (e.g. when an entity is deactivated or deleted).
        """
        if not self.is_available:
            return False
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"Error deleting document {doc_id} from ChromaDB: {e}", exc_info=True)
            return False

    def count(self) -> int:
        if not self.is_available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def reset(self) -> bool:
        """Clear all documents in collection (useful for testing or rebuilding index)."""
        if not self.is_available:
            return False
        try:
            collection_name = getattr(settings, 'CHROMA_COLLECTION_NAME', 'ac_shop_knowledge')
            self._client.delete_collection(name=collection_name)
            self._collection = self._client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except Exception as e:
            logger.error(f"Error resetting ChromaDB collection: {e}", exc_info=True)
            return False
