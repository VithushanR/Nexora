"""
Shared sentence-embedding helper.

Used by Agent 3 (shortlisting plausible contradiction pairs) and Agent 4
(clustering limitation statements), and available to Report Assembly for
its FAISS index. Deliberately not part of llm/client.py: embeddings are
free, local and deterministic, whereas that module wraps a metered API and
carries a budget-exhaustion flag. Keeping them apart keeps the project's
"LLM calls only for genuine judgment" boundary visible in the imports.

The model is loaded lazily and cached process-wide. Importing this module
must stay cheap -- SentenceTransformer downloads weights on first use, and
a test run that never embeds anything should never pay that cost.
"""

import asyncio
import logging
import os
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger("nexora.embeddings")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_model = None


class EmbeddingUnavailableError(Exception):
    """Raised when the embedding model cannot be loaded (no weights cached
    and no network, unsupported platform, etc.). Callers degrade honestly
    rather than silently skipping the step that needed it."""


def get_model():
    """Loads and caches the sentence-transformer. Blocking -- call via
    embed(), which pushes it to a thread."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model %s", EMBEDDING_MODEL)
            _model = SentenceTransformer(EMBEDDING_MODEL)
        except Exception as e:
            raise EmbeddingUnavailableError(
                f"Could not load embedding model {EMBEDDING_MODEL}: {e}"
            ) from e
    return _model


async def embed(texts: Sequence[str]) -> np.ndarray:
    """Returns an (n, dim) array of L2-normalised embeddings, so a plain
    dot product between two rows is their cosine similarity.

    Raises EmbeddingUnavailableError if the model can't be loaded.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    model = await asyncio.to_thread(get_model)
    vectors = await asyncio.to_thread(
        model.encode, list(texts), normalize_embeddings=True, show_progress_bar=False
    )
    return np.asarray(vectors, dtype=np.float32)


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity. Assumes rows are already normalised (as
    embed() returns them), so this is just the Gram matrix."""
    if vectors.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    return vectors @ vectors.T


def reset_model_cache_for_tests() -> None:
    """Test-only helper -- production code should never drop the cache."""
    global _model
    _model = None


def set_model_for_tests(model: Optional[object]) -> None:
    """Test-only helper: inject a stub encoder so tests can exercise the
    similarity path without downloading real weights."""
    global _model
    _model = model
