"""RAG ingestion: chunk HKMA AML/CFT Guideline by paragraph + embed + persist to Chroma.

Run once after corpus changes:
    python -m backend.rag.ingest

Chunks the HKMA AML/CFT Guideline for Licensed Stablecoin Issuers along its native
paragraph boundaries (4.34, 5.10(c), 7.5, etc.). Each chunk's text is embedded via
Gemini's `gemini-embedding-2` model (3072-dim) and persisted to a local Chroma store.
The Chroma collection is the retrieval source for the Risk Sentinel agents (M3-A).

Cap 656 ingestion is deferred — its language is licensing-tier and not load-bearing
for transaction-level AML decisions. Add to corpus later if traceability gaps appear.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import PROJECT_ROOT, Settings, get_settings

logger = logging.getLogger(__name__)

EMBED_MODEL = "gemini-embedding-2"
EMBED_THROTTLE_SECONDS = 0.7  # ~85 RPM, well under free-tier 100 RPM cap

# Matches paragraph headers like "4.34.", "5.10(c).", optionally followed by punctuation.
# Anchored to line start, with optional whitespace before.
PARAGRAPH_HEADER = re.compile(
    r"(?m)^\s*(\d+\.\d+(?:\([a-z]\))?)\.\s+([A-Z(\"'])"
)
PAGE_MARKER = re.compile(r"===== PAGE \d+ =====")
# strip "...... 99" TOC dot-leaders
TOC_DOT_LEADER = re.compile(r"\.{3,}\s*\d+\s*$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    paragraph_id: str
    document: str
    text: str


def clean_corpus(raw: str) -> str:
    """Remove page markers and collapse whitespace."""
    text = PAGE_MARKER.sub("", raw)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def chunk_by_paragraph(text: str, document: str, *, min_len: int = 80) -> list[Chunk]:
    """Slice text along paragraph headers; emit one Chunk per paragraph."""
    matches = list(PARAGRAPH_HEADER.finditer(text))
    chunks: list[Chunk] = []
    for i, m in enumerate(matches):
        paragraph_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        body = re.sub(r"\s+", " ", body)
        body = TOC_DOT_LEADER.sub("", body).strip()
        if len(body) < min_len:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{document}::{paragraph_id}",
                paragraph_id=paragraph_id,
                document=document,
                text=body,
            )
        )
    return chunks


@retry(
    stop=stop_after_attempt(6),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type(genai_errors.ClientError),
    reraise=True,
)
def _embed_one(client: genai.Client, text: str) -> list[float]:
    resp = client.models.embed_content(model=EMBED_MODEL, contents=text)
    return resp.embeddings[0].values


def embed_batch(client: genai.Client, texts: list[str]) -> list[list[float]]:
    """Embed strings via Gemini one at a time with throttling + retry on 429.

    The Gemini Python SDK's ``embed_content`` treats a list ``contents`` as multi-part
    content for a single embedding, not as a batch. We loop with a delay to stay
    under the free-tier rate limit.
    """
    out: list[list[float]] = []
    for i, t in enumerate(texts):
        out.append(_embed_one(client, t))
        if (i + 1) % 25 == 0 or (i + 1) == len(texts):
            logger.info("  embedded %d/%d", i + 1, len(texts))
        time.sleep(EMBED_THROTTLE_SECONDS)
    return out


def ingest(settings: Settings) -> dict[str, int]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY missing from .env")

    gemini = genai.Client(api_key=settings.gemini_api_key)
    chroma = chromadb.PersistentClient(path=settings.rag_chroma_path)
    col = chroma.get_or_create_collection(
        name=settings.rag_collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    results: dict[str, int] = {}
    corpus_files = [
        (PROJECT_ROOT / "_extracted" / "aml_guideline.txt", "HKMA-AML-Guideline-2025-08"),
    ]
    for path, document in corpus_files:
        if not path.exists():
            logger.warning("Corpus file missing, skipping: %s", path)
            continue
        raw = path.read_text(encoding="utf-8")
        cleaned = clean_corpus(raw)
        chunks = chunk_by_paragraph(cleaned, document)
        logger.info("%s -> %d paragraph chunks", document, len(chunks))
        if not chunks:
            results[document] = 0
            continue

        embeddings = embed_batch(gemini, [c.text for c in chunks])
        col.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {"paragraph_id": c.paragraph_id, "document": c.document}
                for c in chunks
            ],
        )
        results[document] = len(chunks)
        logger.info("Upserted %d chunks into Chroma collection %r", len(chunks), col.name)

    logger.info("Collection size: %d", col.count())
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    load_dotenv()
    settings = get_settings()
    stats = ingest(settings)
    print("\nIngestion complete:")
    for doc, n in stats.items():
        print(f"  {doc}: {n} chunks")


if __name__ == "__main__":
    main()
