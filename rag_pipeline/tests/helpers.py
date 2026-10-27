"""
Shared test helpers.

The real tests must not call the internet or need a built database, so:
  * FakeCollection  behaves like a ChromaDB collection (cosine search + language filter)
                    but is built in memory from the real knowledge base files.
  * StubLLM         behaves like the Groq client, but returns a fixed reply or raises an error.
"""

import os
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Test-only secrets (never real ones).
os.environ["TOKEN_SECRET"] = "unit-test-secret-not-for-production"
os.environ["ACCESS_CODES"] = "SUB-TEST-1, SUB-TEST-2"
os.environ["ADMIN_ACCESS_CODE"] = "ADMIN-TEST-CODE"
os.environ.pop("GROQ_API_KEY", None)

import ingest                                  # noqa: E402
from embedder import TFIDFEmbedder, normalise  # noqa: E402


def build_embedder_and_records():
    records = ingest.load_markdown_chunks()
    embedder = TFIDFEmbedder()
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        embedder.fit([normalise(r["text"]) for r in records])
    return embedder, records


class FakeCollection:
    """In-memory stand-in for a ChromaDB collection (cosine distance)."""

    def __init__(self, embedder, records):
        self.docs = [r["text"] for r in records]
        self.metas = [r["metadata"] for r in records]
        self.vecs = np.array([embedder.embed(normalise(r["text"])) for r in records])
        self.queries = []

    def count(self):
        return len(self.docs)

    def get(self, include=None):
        return {"ids": [str(i) for i in range(len(self.docs))], "metadatas": list(self.metas)}

    def query(self, query_embeddings, n_results, where=None, include=None):
        self.queries.append({"n_results": n_results, "where": where})
        q = np.array(query_embeddings[0])
        idx = [i for i, m in enumerate(self.metas)
               if not where or all(m.get(k) == v for k, v in where.items())]
        sims = self.vecs[idx] @ q
        order = np.argsort(-sims)[:n_results]
        chosen = [idx[o] for o in order]
        return {
            "documents": [[self.docs[i] for i in chosen]],
            "metadatas": [[self.metas[i] for i in chosen]],
            "distances": [[float(1.0 - sims[o]) for o in order]],
        }


class StubLLM:
    """Stand-in for the Groq client."""

    def __init__(self, reply="Stub answer.\nNext step: call 8202.", error=None):
        self.reply = reply
        self.error = error
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        message = types.SimpleNamespace(content=self.reply)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class FakeTimeout(Exception):
    """Pretends to be a network timeout from the model provider."""
