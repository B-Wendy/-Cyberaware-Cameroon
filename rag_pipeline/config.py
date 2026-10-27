"""
config.py
All the settings of the project in ONE place, so nothing is "hidden" in the code.

Secrets (API key, access codes, token secret) are NOT written here.  They are
read from environment variables, which come from the .env file on your own
computer and from the Render dashboard when the app is online.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# Where the knowledge base lives, and where the search index is stored.
# STORE_PATH can be changed with an environment variable; by default the index
# is stored inside the project folder.
KB_DIR        = BASE_DIR / "knowledge_base"
STORE_DIR     = Path(os.getenv("STORE_PATH", str(BASE_DIR)))
CHROMA_DIR    = STORE_DIR / "chroma_db"
EMBEDDER_PATH = STORE_DIR / "tfidf_embedder.json"
LESSONS_PATH  = BASE_DIR / "lessons.json"
TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"

# Retrieval settings (Section 4.4.4 of the dissertation)
COLLECTION_NAME = "cyberaware"
TOP_K           = 4       # how many passages are fetched for each question
MIN_SIMILARITY  = 0.10    # passages scoring below this are thrown away (chosen with evaluate.py)

# Generation settings (Section 4.4.5)
CHAT_MODEL   = "openai/gpt-oss-20b"   # Groq retired llama-3.1-8b-instant on 16 Aug 2026 and names this as its replacement
TEMPERATURE  = 0.2        # low = more predictable, factual answers
MAX_TOKENS   = 1000       # caps the whole reply. gpt-oss spends part of it on its own reasoning, so 600 was too small
REASONING_EFFORT = "low"  # gpt-oss only: keep the hidden reasoning short so the answer is not cut off
LLM_TIMEOUT  = 20.0       # seconds to wait for the model before giving up

# Safety limits (Section 4.4.12)
MAX_QUESTION_CHARS = 500  # longest question the chatbot accepts
CHAT_LIMIT_PER_MIN = 20   # chat requests per visitor per minute
CODE_LIMIT_PER_MIN = 5    # access-code attempts per visitor per minute

# Behind a hosting platform every request arrives from the platform's own proxy,
# so the visitor's real address is in the X-Forwarded-For header.  A visitor can
# also forge that header, so we only trust the entry added by OUR proxy: the
# one that many positions from the right.  0 = do not use the header at all
# (right for running on your own computer); on Render set PROXY_HOPS=1.
PROXY_HOPS = int(os.getenv("PROXY_HOPS", "0") or 0)

# Subscription (Section 4.4.8)
PRICE_FCFA   = 2500
PASS_PERCENT = 80         # quiz score needed to pass a lesson
