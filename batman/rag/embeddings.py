"""Pluggable embeddings.

Default: HashingEmbeddings — a lightweight, dependency-free hashing/bag-of-words
vectorizer (deterministic, no torch). Good enough for small-KB retrieval.

Scaffolding: SentenceTransformerEmbeddings — opt-in high-quality embeddings.
Selected via BATMAN_EMBEDDINGS_BACKEND=sentence_transformers.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from batman.config import Settings, get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embeddings:
    dim: int = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


class HashingEmbeddings(Embeddings):
    """Feature-hashing bag-of-words with L2 normalization. Deterministic."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _hash(self, token: str) -> int:
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(h, 16) % self.dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=float)
        for i, text in enumerate(texts):
            for tok in _tokenize(text):
                out[i, self._hash(tok)] += 1.0
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


class SentenceTransformerEmbeddings(Embeddings):
    """Opt-in wrapper around sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=float)


def get_embeddings(settings: Settings | None = None) -> Embeddings:
    settings = settings or get_settings()
    backend = (settings.embeddings_backend or "hashing").lower()
    if backend == "sentence_transformers":
        try:
            return SentenceTransformerEmbeddings(settings.sentence_transformers_model)
        except Exception:
            # Fall back to the lightweight default if the heavy dep is missing.
            return HashingEmbeddings()
    return HashingEmbeddings()
