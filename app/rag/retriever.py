"""ChromaDB retriever for optimization patterns."""
import logging
from typing import List, Dict, Any, Optional

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except ImportError:  # pragma: no cover - optional dependency for tests/template mode
    chromadb = None
    ChromaSettings = None

from app.config import settings
from app.rag.patterns import get_all_patterns, get_patterns_by_service

logger = logging.getLogger(__name__)


class PatternRetriever:
    """Retrieve cost optimization patterns from ChromaDB."""

    def __init__(self):
        self._client = None
        self._collection = None

    @property
    def client(self):
        if chromadb is None or ChromaSettings is None:
            raise RuntimeError("chromadb is not installed")
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def initialize_patterns(self, embeddings) -> int:
        """Populate ChromaDB with optimization patterns."""
        patterns = get_all_patterns()
        if not patterns:
            return 0

        ids = [p["id"] for p in patterns]
        documents = [p["content"] for p in patterns]
        metadatas = [
            {
                "id": p["id"],
                "category": p["category"],
                "services": ",".join(p["services"]),
            }
            for p in patterns
        ]

        # Generate embeddings
        embeds = embeddings.embed_documents(documents)

        # Upsert (delete + add to avoid duplicates)
        try:
            self.collection.delete(ids=ids)
        except Exception:
            pass

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeds,
            metadatas=metadatas,
        )
        logger.info("Initialized %d optimization patterns in ChromaDB", len(patterns))
        return len(patterns)

    def retrieve(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        service_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant optimization patterns."""
        where = None
        if service_filter:
            # ChromaDB doesn't support array contains directly; filter post-query
            pass

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        dists = results.get("distances") or [[]]

        for text, meta, dist in zip(docs[0], metas[0], dists[0]):
            hits.append({
                "content": text,
                "metadata": meta or {},
                "distance": dist,
            })

        # Post-filter by service if provided
        if service_filter:
            filtered = []
            for hit in hits:
                services = hit["metadata"].get("services", "").split(",")
                if "*" in services or service_filter in services:
                    filtered.append(hit)
            return filtered[:top_k]

        return hits

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0


_retriever: Optional[PatternRetriever] = None


def get_retriever() -> PatternRetriever:
    global _retriever
    if _retriever is None:
        _retriever = PatternRetriever()
    return _retriever