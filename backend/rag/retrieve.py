"""RAG retrieval: top-K HKMA paragraph search via Chroma + Gemini embeddings.

The retriever is the bridge between the agent's runtime context (transfer + profiles +
sanctions) and the regulatory corpus. Agents that consume its output must cite only
``paragraph_id`` values present in the returned chunks — anything else is hallucination.

CLI smoke test (verifies retrieval quality):
    python -m backend.rag.retrieve "unhosted wallet sanctions screening"
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import chromadb
from dotenv import load_dotenv
from google import genai

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

EMBED_MODEL = "gemini-embedding-2"


@dataclass(frozen=True)
class RetrievedChunk:
    paragraph_id: str
    document: str
    text: str
    similarity: float  # higher is better; cosine-space, ~[0, 1]


class HKMARetriever:
    """Thin sync wrapper over Chroma + Gemini embeddings."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self._chroma = chromadb.PersistentClient(path=settings.rag_chroma_path)
        self._col = self._chroma.get_collection(name=settings.rag_collection_name)

    def collection_size(self) -> int:
        return self._col.count()

    def retrieve(self, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        resp = self._gemini.models.embed_content(model=EMBED_MODEL, contents=query)
        query_emb = resp.embeddings[0].values

        result = self._col.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )

        ids = result["ids"][0]
        metas = result["metadatas"][0]
        docs = result["documents"][0]
        dists = result["distances"][0]

        out: list[RetrievedChunk] = []
        for i in range(len(ids)):
            out.append(
                RetrievedChunk(
                    paragraph_id=str(metas[i].get("paragraph_id", "")),
                    document=str(metas[i].get("document", "")),
                    text=str(docs[i]),
                    similarity=max(0.0, 1.0 - float(dists[i])),
                )
            )
        return out


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="natural language query")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    load_dotenv()
    settings = get_settings()
    retriever = HKMARetriever(settings)
    print(f"Collection size: {retriever.collection_size()} chunks")

    query = " ".join(args.query)
    print(f"\nQuery: {query}")
    print(f"Top-{args.top_k} results:\n")

    hits = retriever.retrieve(query, top_k=args.top_k)
    for h in hits:
        snippet = h.text[:140].replace("\n", " ")
        print(f"  [{h.paragraph_id:>10}]  sim={h.similarity:.3f}  {snippet}...")

    if not hits:
        sys.exit(1)


if __name__ == "__main__":
    _cli()
