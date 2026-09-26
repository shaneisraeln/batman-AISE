"""RAG retriever.

Indexes the knowledge base with the configured embeddings backend and retrieves
top-k passages by cosine similarity. Supports an in-memory vector store (default)
and Chroma (opt-in via BATMAN_VECTOR_STORE=chroma).
"""

from __future__ import annotations

import numpy as np

from batman.config import Settings, get_settings
from batman.rag.embeddings import Embeddings, get_embeddings
from batman.rag.knowledge_base import Document, all_chunks


class Retriever:
    def __init__(
        self,
        embeddings: Embeddings | None = None,
        settings: Settings | None = None,
        docs: list[Document] | None = None,
    ):
        self.settings = settings or get_settings()
        self.embeddings = embeddings or get_embeddings(self.settings)
        self.docs = docs or all_chunks()
        self._matrix: np.ndarray | None = None
        self._backend = "memory"
        self._chroma_collection = None
        self._build_index()

    def _build_index(self) -> None:
        texts = [d.text for d in self.docs]
        if (self.settings.vector_store or "memory").lower() == "chroma":
            if self._try_build_chroma(texts):
                self._backend = "chroma"
                return
        # In-memory fallback / default.
        self._matrix = self.embeddings.embed(texts)
        self._backend = "memory"

    def _try_build_chroma(self, texts: list[str]) -> bool:
        try:
            import chromadb  # type: ignore

            client = chromadb.EphemeralClient()
            col = client.get_or_create_collection("batman_kb")
            vecs = self.embeddings.embed(texts).tolist()
            col.add(
                ids=[d.doc_id for d in self.docs],
                documents=texts,
                embeddings=vecs,
                metadatas=[{"category": d.category} for d in self.docs],
            )
            self._chroma_collection = col
            return True
        except Exception:
            return False

    def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        top_k = top_k or self.settings.rag_top_k
        if not query:
            return []
        q = self.embeddings.embed_one(query)

        if self._backend == "chroma" and self._chroma_collection is not None:
            try:
                res = self._chroma_collection.query(
                    query_embeddings=[q.tolist()], n_results=top_k
                )
                docs = res.get("documents", [[]])
                return docs[0] if docs else []
            except Exception:
                pass  # fall through to memory if chroma query fails

        if self._matrix is None:
            self._matrix = self.embeddings.embed([d.text for d in self.docs])
        sims = self._matrix @ q  # both L2-normalized => cosine similarity
        order = np.argsort(-sims)[:top_k]
        return [self.docs[i].text for i in order]

    @property
    def backend(self) -> str:
        return self._backend
