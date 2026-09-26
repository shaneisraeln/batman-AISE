from batman.rag.embeddings import HashingEmbeddings
from batman.rag.retriever import Retriever


def test_hashing_embeddings_deterministic_and_normalized():
    emb = HashingEmbeddings(dim=128)
    v1 = emb.embed_one("model extraction attack")
    v2 = emb.embed_one("model extraction attack")
    assert v1.shape == (128,)
    assert (v1 == v2).all()
    import numpy as np

    assert abs(np.linalg.norm(v1) - 1.0) < 1e-6


def test_retriever_returns_relevant_docs():
    r = Retriever()
    results = r.retrieve("model extraction high query diversity probing", top_k=3)
    assert len(results) <= 3
    assert len(results) >= 1
    # The top result should mention extraction concepts.
    joined = " ".join(results).lower()
    assert "extraction" in joined or "surrogate" in joined


def test_retriever_empty_query():
    r = Retriever()
    assert r.retrieve("", top_k=3) == []
