"""
CyberAware Cameroon — FastAPI backend (the "waiter").

The waiter takes requests from the web page, asks the right helper file to do
the work, and brings back the answer.  The menu of requests it understands
(Table 4.9 of the dissertation):

    GET   /                     the web page itself
    POST  /api/chat             ask the chatbot a question
    GET   /api/lessons          list of lessons (with locked / unlocked state)
    GET   /api/lessons/{id}     one lesson            (402 if it is locked)
    POST  /api/quiz/submit      mark a quiz on the server
    POST  /api/subscribe        exchange an access code for an access token
    GET   /api/certificate      certificate data once all 10 lessons are passed
    GET   /api/health           is the service (and the knowledge base) alive?

Run on your computer:   uvicorn app:app --reload
"""

import logging
import os
import re
from datetime import date
from typing import Annotated, List, Optional

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, StringConstraints

import access
from config import (CHAT_LIMIT_PER_MIN, CODE_LIMIT_PER_MIN, COLLECTION_NAME,
                    MAX_QUESTION_CHARS, PASS_PERCENT, PRICE_FCFA, PROXY_HOPS, TEMPLATE_PATH)
from lessons import LessonStore
from rag import SUPPORTED, answer_question, get_collection
from ratelimit import RateLimiter

log = logging.getLogger("cyberaware.app")

app = FastAPI(title="CyberAware Cameroon API")

store = LessonStore()                       # loads + checks lessons.json at start-up
chat_limiter = RateLimiter(CHAT_LIMIT_PER_MIN)
code_limiter = RateLimiter(CODE_LIMIT_PER_MIN)

RATE_MESSAGE = {
    "en": "Too many requests. Please wait a minute.",
    "fr": "Trop de requêtes. Veuillez attendre une minute.",
    "pidgin": "You don ask too many. Wait small before you ask again.",
}
BUSY_MESSAGE = {
    "en": "The assistant is not available right now. Please try again in a moment, or call CIRT-Cameroun on 8202 (free).",
    "fr": "L'assistant n'est pas disponible pour le moment. Réessayez dans un instant ou appelez le CIRT-Cameroun au 8202 (gratuit).",
    "pidgin": "The assistant no dey available now. Try again small time, or call CIRT-Cameroun for 8202 (free).",
}

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def client_ip(request: Request) -> str:
    """Who is asking?  Used to rate-limit each visitor separately.

    Normally the address of the connection.  Behind a hosting proxy (PROXY_HOPS>0)
    it is the entry of X-Forwarded-For added by our own proxy, counted from the
    RIGHT, because anything a visitor writes into that header ends up on the left.
    """
    peer = request.client.host if request.client else "unknown"
    if PROXY_HOPS > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= PROXY_HOPS:
            return parts[-PROXY_HOPS]
    return peer


def lang_of(value) -> str:
    value = (value or "").strip().lower()
    return value if value in SUPPORTED else "en"


def passed_ids(best: dict) -> list:
    """Lessons whose best score reaches the pass mark."""
    out = []
    for lesson_id, score in best.items():
        if store.exists(lesson_id):
            total = len(store.body(lesson_id)["quiz"])
            if round(100 * score / total) >= PASS_PERCENT:
                out.append(lesson_id)
    return sorted(out)


def completed_all(best: dict) -> bool:
    return len(passed_ids(best)) == store.count()


def payment_required():
    return JSONResponse(status_code=402,
                        content={"detail": "payment_required", "price_fcfa": PRICE_FCFA})


# ──────────────────────────────────────────────────────────────
# Safety headers on every response
# ──────────────────────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme) if PROXY_HOPS > 0 else request.url.scheme
    if scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ──────────────────────────────────────────────────────────────
# GET /   the web page
# ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html, headers={"Content-Security-Policy": CSP})


# ──────────────────────────────────────────────────────────────
# POST /api/chat
# ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    # The text is trimmed first, then must be 1..500 characters.
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                              max_length=MAX_QUESTION_CHARS)]
    language: str = "auto"


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    if not chat_limiter.allow(client_ip(request)):
        return JSONResponse(status_code=429, content={
            "answer": RATE_MESSAGE[lang_of(req.language)], "sources": [],
            "mode": "rate_limited", "language": lang_of(req.language)})
    try:
        return answer_question(req.message, req.language)
    except Exception:
        # Typical cause: the knowledge base has not been built (python ingest.py).
        log.exception("Chat failed")
        lang = lang_of(req.language)
        return JSONResponse(status_code=503, content={
            "answer": BUSY_MESSAGE[lang], "sources": [], "mode": "unavailable", "language": lang})


# ──────────────────────────────────────────────────────────────
# Lessons
# ──────────────────────────────────────────────────────────────

@app.get("/api/lessons")
async def list_lessons(
    x_access_token: Optional[str] = Header(default=None),
    x_progress_token: Optional[str] = Header(default=None),
):
    status, payload = access.access_status(x_access_token)
    entitled = status == "valid"
    best = access.read_progress(x_progress_token)
    return {
        "lessons": store.catalogue(entitled),
        "entitled": entitled,
        "tier": payload.get("tier") if entitled else None,
        "expires_at": payload.get("exp") if entitled else None,
        "token_status": status,
        "pass_percent": PASS_PERCENT,
        "progress": {str(k): v for k, v in best.items()},
        "passed": passed_ids(best),
        "completed_all": completed_all(best),
        "payment": {
            "price_fcfa": PRICE_FCFA,
            "number": os.getenv("PAYMENT_NUMBER", "+237 6XX XXX XXX"),
            "reference": os.getenv("PAYMENT_REFERENCE", "CYBER-LEARN"),
        },
    }


@app.get("/api/lessons/{lesson_id}")
async def get_lesson(lesson_id: int, x_access_token: Optional[str] = Header(default=None)):
    if not store.exists(lesson_id):
        return JSONResponse(status_code=404, content={"detail": "lesson_not_found"})
    if not store.is_free(lesson_id) and not access.is_entitled(x_access_token):
        return payment_required()               # 402 - and NO lesson content is sent
    return store.body(lesson_id)


# ──────────────────────────────────────────────────────────────
# POST /api/quiz/submit
# ──────────────────────────────────────────────────────────────

class QuizSubmission(BaseModel):
    lesson_id: int
    answers: List[int] = Field(min_length=1, max_length=20)


@app.post("/api/quiz/submit")
async def submit_quiz(
    sub: QuizSubmission,
    x_access_token: Optional[str] = Header(default=None),
    x_progress_token: Optional[str] = Header(default=None),
):
    if not store.exists(sub.lesson_id):
        return JSONResponse(status_code=404, content={"detail": "lesson_not_found"})
    if not store.is_free(sub.lesson_id) and not access.is_entitled(x_access_token):
        return payment_required()
    try:
        result = store.grade(sub.lesson_id, sub.answers)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    best = access.read_progress(x_progress_token)
    best[sub.lesson_id] = max(best.get(sub.lesson_id, 0), result["score"])
    result.update({
        "lesson_id": sub.lesson_id,
        "best_score": best[sub.lesson_id],
        "progress": {str(k): v for k, v in sorted(best.items())},
        "passed_lessons": passed_ids(best),
        "completed_all": completed_all(best),
        "progress_token": access.issue_progress_token(best),
        "pass_percent": PASS_PERCENT,
    })
    return result


# ──────────────────────────────────────────────────────────────
# POST /api/subscribe
# ──────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


@app.post("/api/subscribe")
async def subscribe(req: SubscribeRequest, request: Request):
    if not code_limiter.allow(client_ip(request)):
        return JSONResponse(status_code=429, content={"valid": False, "detail": "too_many_attempts"})
    tier = access.check_code(req.code)
    if tier is None:
        return JSONResponse(status_code=403, content={"valid": False})
    issued = access.issue_access_token(tier)
    return {"valid": True, **issued}


# ──────────────────────────────────────────────────────────────
# GET /api/certificate
# ──────────────────────────────────────────────────────────────

_NAME = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .'\-])*")


@app.get("/api/certificate")
async def certificate(
    name: str,
    x_access_token: Optional[str] = Header(default=None),
    x_progress_token: Optional[str] = Header(default=None),
):
    if not access.is_entitled(x_access_token):
        return payment_required()
    name = re.sub(r"\s+", " ", name or "").strip()
    if not (2 <= len(name) <= 60) or not _NAME.fullmatch(name):
        return JSONResponse(status_code=422, content={"detail": "invalid_name"})

    best = access.read_progress(x_progress_token)
    done = passed_ids(best)
    if len(done) != store.count():
        missing = [i for i in range(store.count()) if i not in done]
        return JSONResponse(status_code=409, content={"detail": "not_complete", "missing": missing})

    today = date.today().isoformat()
    return {
        "name": name,
        "completed_on": today,
        "reference": access.certificate_reference(name, today, best),
        "pass_percent": PASS_PERCENT,
        "lessons": [
            {"id": i, "name": store.body(i)["name"]["en"],
             "percent": round(100 * best[i] / len(store.body(i)["quiz"]))}
            for i in range(store.count())
        ],
    }


# ──────────────────────────────────────────────────────────────
# GET /api/health
# ──────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    info = {"service": "CyberAware Cameroon", "lessons": store.count(),
            "collection": COLLECTION_NAME}
    try:
        info["chunks"] = get_collection().count()
        info["knowledge_base_ready"] = info["chunks"] > 0
    except Exception:
        info["chunks"] = 0
        info["knowledge_base_ready"] = False
    info["status"] = "ok" if info["knowledge_base_ready"] else "degraded"
    return JSONResponse(status_code=200 if info["knowledge_base_ready"] else 503, content=info)
