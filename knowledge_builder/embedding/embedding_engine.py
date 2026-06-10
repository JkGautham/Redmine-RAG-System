"""
Task 2.8 — Embedding Engine

Generates dense vectors for chunks using bge-small-en-v1.5.
Stores embeddings + metadata in ChromaDB.

Model runs on CPU — no VRAM competition with Ollama.
"""

import logging

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from config import (
    CHROMA_PATH,
    CHROMA_COLLECTION,
    EMBEDDING_MODEL,
    EMBEDDING_BATCH_SIZE,
    ENABLE_CHROMA,
)

logger = logging.getLogger("knowledge_builder.embedding")

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("[Embedding] Loading model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("[Embedding] Model ready")
    return _model


class EmbeddingEngine:
    """Embed chunks and persist to ChromaDB."""

    def __init__(self):
        if not ENABLE_CHROMA:
            self._collection = None
            logger.info("[Embedding] ChromaDB disabled via config")
            return

        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "[Embedding] ChromaDB ready — collection '%s' at %s",
            CHROMA_COLLECTION, CHROMA_PATH,
        )

    def embed_and_store(self, chunks: list[dict]) -> int:
        """
        Embed all chunks and upsert into ChromaDB.

        Args:
            chunks: List of chunk dicts from ChunkBuilder.

        Returns:
            Number of chunks successfully stored.
        """
        if not ENABLE_CHROMA or self._collection is None:
            return 0

        if not chunks:
            return 0

        model = _get_model()

        stored = 0

        # Batch processing
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            ids   = [c["chunk_id"] for c in batch]
            metas = [c["metadata"] for c in batch]

            try:
                embeddings = model.encode(
                    texts,
                    batch_size=EMBEDDING_BATCH_SIZE,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                ).tolist()

                self._collection.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metas,
                )

                stored += len(batch)

                logger.debug(
                    "[Embedding] Batch %d/%d stored (%d chunks)",
                    i // EMBEDDING_BATCH_SIZE + 1,
                    (len(chunks) - 1) // EMBEDDING_BATCH_SIZE + 1,
                    len(batch),
                )

            except Exception as e:
                logger.error(
                    "[Embedding] Failed to store batch starting at index %d: %s",
                    i, e,
                )

        return stored
