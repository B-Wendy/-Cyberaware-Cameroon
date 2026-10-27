"""
ingest.py
Parses the markdown knowledge base (EN + FR, and optional PCM = Pidgin sections)
into chunks and stores them
in ChromaDB using offline TF-IDF embeddings (no internet / no API needed).

Run once, and again whenever you edit knowledge_base files:
    python ingest.py

It REBUILDS the index from scratch each time (it deletes the old collection
first), so old, stale vectors can never be left behind.
"""

import re

from config import KB_DIR, CHROMA_DIR, EMBEDDER_PATH, COLLECTION_NAME
from embedder import TFIDFEmbedder, normalise

SKIP_FILES = {"00_README.md", "sources.md", "faq_dataset.csv"}
MAX_WORDS_PER_CHUNK = 180
REQUIRED_FRONTMATTER = ("topic", "source", "last_updated")
REQUIRED_LANGUAGES = ("EN", "FR")
OPTIONAL_LANGUAGES = ("PCM",)      # Cameroonian Pidgin: used when a topic file has a "## PCM" section


class CorpusError(Exception):
    """Raised when a knowledge-base file is missing something it must have."""


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
    parts = re.split(r"^##\s+(EN|FR|PCM)\s*$", body, flags=re.MULTILINE)
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


def validate_file(path_name: str, meta: dict, sections: dict):
    """Stop with a clear message if a file is missing required information.
    This is what keeps a half-finished file from silently entering the index."""
    missing = [k for k in REQUIRED_FRONTMATTER if not meta.get(k)]
    if missing:
        raise CorpusError(f"{path_name}: missing frontmatter field(s): {', '.join(missing)}")
    lacking = [l for l in REQUIRED_LANGUAGES if not sections.get(l)]
    if lacking:
        raise CorpusError(f"{path_name}: missing language section(s): {', '.join(lacking)} "
                          f"(every topic needs both EN and FR)")


def load_markdown_chunks(kb_dir=None):
    kb_dir = kb_dir or KB_DIR
    records = []
    for path in sorted(kb_dir.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        sections = split_by_language(body)
        validate_file(path.name, meta, sections)
        for lang, content in sections.items():
            for i, chunk in enumerate(chunk_text(content)):
                records.append({
                    "id": f"{path.stem}_{lang}_{i}",
                    "text": chunk,
                    "metadata": {
                        "source_file": path.name,
                        "topic":       meta["topic"],
                        "language":    lang,
                        "source_url":  meta["source"],
                        "review_date": meta["last_updated"],
                    },
                })
    return records


def check_counterparts(records: list) -> list:
    """Return warnings for topics whose EN and FR parts differ in size."""
    counts = {}
    for r in records:
        key = (r["metadata"]["source_file"], r["metadata"]["language"])
        counts[key] = counts.get(key, 0) + 1
    warnings = []
    for fname in sorted({k[0] for k in counts}):
        en, fr = counts.get((fname, "EN"), 0), counts.get((fname, "FR"), 0)
        if en != fr:
            warnings.append(f"{fname}: {en} EN chunk(s) but {fr} FR chunk(s)")
    return warnings


def main():
    if not KB_DIR.exists():
        raise RuntimeError(f"Knowledge base folder not found at {KB_DIR}")

    records = load_markdown_chunks()
    if not records:
        raise RuntimeError("No chunks parsed. Check your markdown files.")

    print(f"Parsed {len(records)} chunks from {KB_DIR}")
    for r in records[:3]:
        print(f"  {r['id']} | {r['metadata']['topic']} | {r['metadata']['language']}")
    for w in check_counterparts(records):
        print(f"  note: {w}")

    # Build and save TF-IDF embedder
    print("\nBuilding TF-IDF embeddings (offline, no internet needed)...")
    embedder = TFIDFEmbedder()
    texts = [normalise(r["text"]) for r in records]
    embedder.fit(texts)
    embeddings = embedder.embed_many(texts)
    embedder.save(str(EMBEDDER_PATH))

    # Store in ChromaDB with pre-computed embeddings
    print("\nSaving to ChromaDB...")
    import chromadb   # imported here so the checks above can be tested without it
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Start clean: remove the current collection and the old pre-v2 one ("cyberkb")
    for name in (COLLECTION_NAME, "cyberkb"):
        try:
            client.delete_collection(name)
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
    print("Next: start the app with `uvicorn app:app --reload`.")


if __name__ == "__main__":
    main()
