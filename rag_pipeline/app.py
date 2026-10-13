"""
CyberAware Cameroon — FastAPI Backend
Run: uvicorn app:app --reload
"""

import os
import time
from pathlib import Path
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from rag import answer_question

app = FastAPI(title="CyberAware Cameroon API")

# ── Subscription codes — server-side ONLY, never sent to browser ──
VALID_CODES = {
    "CYBER-2025", "CYBER-001", "CYBER-002", "CYBER-003",
    "CYBER-004", "CYBER-005", "CYBER-006", "CYBER-007",
    "CYBER-008", "CYBER-009", "CYBER-010",
}

# ── Rate limiting: 20 requests per IP per minute ──
_call_log: dict = defaultdict(list)


class ChatRequest(BaseModel):
    message: str
    language: str = "en"


class CodeRequest(BaseModel):
    code: str


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    ip = request.client.host
    now = time.time()
    _call_log[ip] = [t for t in _call_log[ip] if now - t < 60]
    if len(_call_log[ip]) > 20:
        msgs = {
            "en": "Too many requests. Please wait a minute.",
            "fr": "Trop de requetes. Veuillez attendre une minute.",
            "pidgin": "You don ask too many. Wait small before you ask again.",
        }
        return {"answer": msgs.get(req.language, msgs["en"]), "sources": []}
    _call_log[ip].append(now)
    result = answer_question(req.message, req.language)
    return result


@app.post("/validate-code")
async def validate_code(req: CodeRequest):
    code = req.code.strip().upper()
    if code in VALID_CODES:
        return {"valid": True}
    return {"valid": False}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "CyberAware Cameroon"}   