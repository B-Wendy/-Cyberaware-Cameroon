"""
rag.py
Retrieval using offline TF-IDF embeddings + answer generation via Gemini API.

CLI test:
    py rag.py
"""

import os
from pathlib import Path

import chromadb
from groq import Groq
from dotenv import load_dotenv
from embedder import TFIDFEmbedder

load_dotenv()

BASE_DIR        = Path(__file__).parent
CHROMA_DIR      = BASE_DIR / "chroma_db"
EMBEDDER_PATH   = BASE_DIR / "tfidf_embedder.json"
COLLECTION_NAME = "cyberkb"
CHAT_MODEL      = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """You are a cybersecurity awareness assistant for the general public and \
small businesses in Cameroon, grounded in official ANTIC/CIRT-Cameroun guidance.

Rules:
- Answer ONLY using the CONTEXT provided. Do not use outside knowledge.
- If the context is insufficient, say so and direct the user to CIRT-Cameroun: \
toll-free 8202, email alerts@cirt.antic.cm, or online at incident.cirt.cm.
- Never invent contact details or procedures not in the context.
- Reply in the same language the user wrote in: English, French, or Cameroonian Pidgin.
- Be concise, practical, and reassuring.
- Never ask the user to share a password, PIN, or one-time code.
"""


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(name=COLLECTION_NAME, embedding_function=None)


def retrieve(query: str, k: int = 4) -> list:
    if not EMBEDDER_PATH.exists():
        raise RuntimeError("Embedder not found. Run `py ingest.py` first.")
    embedder = TFIDFEmbedder.load(str(EMBEDDER_PATH))
    query_embedding = embedder.embed(query)
    collection = get_collection()
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    return [
        {"text": doc, "meta": meta}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def build_context(chunks: list) -> str:
    return "\n\n---\n\n".join(
        f"[Topic: {c['meta'].get('topic')} | Lang: {c['meta'].get('language')} | "
        f"Source: {c['meta'].get('source_url')}]\n{c['text']}"
        for c in chunks
    )


def answer_question(query: str, language: str = "en", k: int = 4) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in .env file.")

    lang_instruction = {
        "en":     "You MUST respond in English only.",
        "fr":     "Tu DOIS répondre uniquement en français.",
        "pidgin": "You MUST respond in Cameroonian Pidgin English only. Write natural Pidgin as spoken in Cameroon — not formal English, not French.",
    }.get(language, "You MUST respond in English only.")

    chunks  = retrieve(query, k=k)
    context = build_context(chunks)

    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"LANGUAGE INSTRUCTION: {lang_instruction}\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"USER QUESTION:\n{query}"
    )

    client   = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": full_prompt}],
    )

    return {
        "answer":  response.choices[0].message.content,
        "sources": [c["meta"] for c in chunks],
    }


if __name__ == "__main__":
    print("CyberAware Cameroon Chatbot (CLI). Type 'quit' to exit.\n")
    while True:
        q = input("You: ").strip()
        if q.lower() in {"quit", "exit"}:
            break
        if not q:
            continue
        result = answer_question(q)
        print("\nBot:", result["answer"])
        print("\nSources:")
        for s in result["sources"]:
            print(f"  - {s.get('topic')} ({s.get('language')}) -> {s.get('source_url')}")
        print()
