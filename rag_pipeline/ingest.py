"""
ingest.py
Parses the bilingual markdown knowledge base into chunks and stores them
in ChromaDB using offline TF-IDF embeddings (no internet / no API needed).

Run once, and again whenever you edit knowledge_base files:
    py ingest.py
"""

import os
import re
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from embedder import TFIDFEmbedder

load_dotenv()

BASE_DIR        = Path(__file__).parent
KB_DIR          = BASE_DIR / "knowledge_base"
CHROMA_DIR      = BASE_DIR / "chroma_db"
EMBEDDER_PATH   = BASE_DIR / "tfidf_embedder.json"
COLLECTION_NAME = "cyberkb"

SKIP_FILES = {"00_README.md", "sources.md", "faq_dataset.csv"}
MAX_WORDS_PER_CHUNK = 180


def parse_frontmatter(text: str):
    match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.groups()
    meta = {}
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def split_by_language(body: str):
    sections = {}
    parts = re.split(r"^##\s+(EN|FR)\s*$", body, flags=re.MULTILINE)
    it = iter(parts[1:])
    for lang, content in zip(it, it):
        sections[lang] = content.strip()
    return sections


def chunk_text(text: str, max_words: int = MAX_WORDS_PER_CHUNK):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current, current_len = [], [], 0
    for p in paragraphs:
        words = len(p.split())
        if current and current_len + words > max_words:
            chunks.append("\n\n".join(current))
            current, current_len = [p], words
        else:
            current.append(p)
            current_len += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def load_markdown_chunks():
    records = []
    for path in sorted(KB_DIR.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        sections = split_by_language(body)
        for lang, content in sections.items():
            for i, chunk in enumerate(chunk_text(content)):
                records.append({
                    "id": f"{path.stem}_{lang}_{i}",
                    "text": chunk,
                    "metadata": {
                        "source_file": path.name,
                        "topic":       meta.get("topic", path.stem),
                        "language":    lang,
                        "source_url":  meta.get("source", ""),
                    },
                })
    return records


def main():
    if not KB_DIR.exists():
        raise RuntimeError(f"Knowledge base folder not found at {KB_DIR}")

    records = load_markdown_chunks()
    if not records:
        raise RuntimeError("No chunks parsed. Check your markdown files.")

    print(f"Parsed {len(records)} chunks from {KB_DIR}")
    for r in records[:3]:
        print(f"  {r['id']} | {r['metadata']['topic']} | {r['metadata']['language']}")

    # Build and save TF-IDF embedder
    print("\nBuilding TF-IDF embeddings (offline, no internet needed)...")
    embedder = TFIDFEmbedder()
    texts = [r["text"] for r in records]
    embedder.fit(texts)
    embeddings = embedder.embed_many(texts)
    embedder.save(str(EMBEDDER_PATH))

    # Store in ChromaDB with pre-computed embeddings
    print("\nSaving to ChromaDB...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    # embedding_function=None because we supply our own embeddings
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )

    collection.add(
        ids=[r["id"] for r in records],
        documents=[r["text"] for r in records],
        metadatas=[r["metadata"] for r in records],
        embeddings=embeddings,
    )

    print(f"\nDone! Ingested {len(records)} chunks into ChromaDB at {CHROMA_DIR}")
    print("Next: run `py rag.py` to test the chatbot.")


if __name__ == "__main__":
    main()
