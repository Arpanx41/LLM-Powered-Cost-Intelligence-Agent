"""Ollama embeddings for cost agent."""
import hashlib
import logging
from typing import List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaEmbeddings:
    """Generate embeddings using Ollama's embedding endpoint."""

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embed_model
        self.timeout = timeout or settings.ollama_timeout
        self._embed_url = f"{self.base_url}/api/embeddings"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    async def aembed_query(self, text: str) -> List[float]:
        return await self._aembed(text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return [await self._aembed(t) for t in texts]

    def _embed(self, text: str) -> List[float]:
        payload = {"model": self.model, "prompt": text}
        resp = httpx.post(self._embed_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "embedding" not in data:
            raise ValueError(f"Ollama returned no embedding field: {data}")
        return data["embedding"]

    async def _aembed(self, text: str) -> List[float]:
        payload = {"model": self.model, "prompt": text}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self._embed_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "embedding" not in data:
                raise ValueError(f"Ollama returned no embedding field: {data}")
            return data["embedding"]

    @staticmethod
    def cache_key(text: str, model: str) -> str:
        digest = hashlib.sha256(f"{model}:{text}".encode("utf-8")).hexdigest()
        return f"embed:{digest}"


_embeddings: OllamaEmbeddings | None = None


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings()
    return _embeddings