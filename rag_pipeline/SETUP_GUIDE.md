# Phase 2 — RAG Pipeline: Setup Guide

This is a working starter implementation. I tested the parsing/chunking logic against
your actual `knowledge_base/` files (44 chunks parsed correctly across EN/FR and all 9
topics) — but I could NOT test the embedding/LLM calls themselves, since my environment
has no internet access. Run the steps below on your own machine where you have network
access and an OpenAI API key.

## 1. Install dependencies
```bash
cd rag_pipeline
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Add your API key
```bash
cp .env.example .env
```
Open `.env` and replace `sk-your-key-here` with your real OpenAI API key.

## 3. Ingest the knowledge base
```bash
python ingest.py
```
This reads every file in `knowledge_base/` (except `00_README.md` and `sources.md`),
splits each into EN/FR sections, chunks them, embeds them with
`text-embedding-3-small`, and stores everything in a local persistent ChromaDB at
`chroma_db/`. You should see output like:
```
Parsed 44 chunks from knowledge_base
Ingested 44 chunks into ChromaDB at chroma_db
```
Re-run this any time you edit or add files to `knowledge_base/`.

## 4. Test retrieval + generation from the command line
```bash
python rag.py
```
Try questions like:
- "Someone asked me to forward a WhatsApp code, is that safe?"
- "Comment signaler un piratage de mon compte Facebook ?"
- "What's a strong password?"

Each answer prints the sources it actually retrieved — use this to sanity-check that
retrieval is pulling the right topic before you trust the generated answer.

## 5. Test the API
```bash
uvicorn app:app --reload
```
Open `http://127.0.0.1:8000/docs` for an interactive Swagger UI, or:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I report a hacked Facebook account?"}'
```

## What to check / tune next
- **Retrieval quality**: if answers cite the wrong topic, try increasing `k` in
  `retrieve()` (currently 4) or rephrasing chunk text in the knowledge base for clarity.
- **Hallucination check**: ask something completely outside the knowledge base
  (e.g., "What's the weather in Douala?") and confirm the bot says it doesn't know,
  rather than making something up. This is your grounding test for the dissertation.
- **Language handling**: ask the same question in English, then French, then Pidgin,
  and compare. Pidgin responses are generated on the fly by the LLM (no Pidgin chunks
  in the KB) — flag this honestly as a limitation in your methodology chapter.
- **Cost**: `gpt-4o-mini` + `text-embedding-3-small` are both cheap, but track your
  OpenAI usage dashboard while testing so you don't get surprised.

## Next phase
Once retrieval/generation feels solid, you're ready for **Phase 3 (multilingual
refinement)** and **Phase 4 (web frontend)** — a simple chat UI calling the `/chat`
endpoint above. Come back when you're ready to build that and I can put together a
working frontend (Streamlit is fastest, or a custom HTML/JS widget if you want it to
look more polished for your defense demo).
