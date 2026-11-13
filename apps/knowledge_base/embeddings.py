import logging
from typing import List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class GeminiEmbeddingService:
    """
    Generates text embeddings using the configured Google Gemini embedding model.
    """
    _client = None

    @classmethod
    def _get_client(cls):
        api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
        if not api_key or not api_key.startswith("AIzaSy"):
            return None

        if cls._client is None:
            try:
                from google import genai
                cls._client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize google-genai Client: {e}", exc_info=True)
                return None
        return cls._client

    @classmethod
    def generate_embedding(cls, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for a single string using Gemini API.
        Returns a list of floats (typically 768 dimensions) or None if API fails/not configured.
        """
        if not text or not text.strip():
            return None

        client = cls._get_client()
        if not client:
            logger.debug("GEMINI_API_KEY is not configured or invalid. Skipping remote embedding.")
            return None

        model_name = getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'text-embedding-004')

        try:
            response = client.models.embed_content(
                model=model_name,
                contents=text.strip()
            )
            if hasattr(response, 'embeddings') and response.embeddings:
                return response.embeddings[0].values
            elif hasattr(response, 'embedding') and response.embedding:
                return response.embedding.values
            return None
        except Exception as e:
            logger.warning(f"Error generating Gemini embedding for text: {e}")
            return None

    @classmethod
    def generate_batch_embeddings(cls, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for a batch of strings.
        """
        return [cls.generate_embedding(t) for t in texts]
