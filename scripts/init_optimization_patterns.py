#!/usr/bin/env python3
"""Initialize optimization patterns in ChromaDB vector store."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.rag.retriever import PatternRetriever
from app.services.embeddings import OllamaEmbeddings


def main():
    print("Initializing optimization patterns in ChromaDB...")
    print(f"ChromaDB host: {settings.chroma_host}:{settings.chroma_port}")

    embeddings = OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
    )
    retriever = PatternRetriever()

    try:
        count = retriever.initialize_patterns(embeddings)
        print(f"Successfully initialized {count} optimization patterns!")
    except Exception as e:
        print(f"Error initializing patterns: {e}")
        print("Make sure ChromaDB is running (docker compose up chromadb)")
        sys.exit(1)


if __name__ == "__main__":
    main()