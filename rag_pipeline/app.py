"""
app.py
FastAPI backend — serves the chat web interface at GET /
and the RAG chatbot API at POST /chat

Run:
    uvicorn app:app --reload
Then open http://127.0.0.1:8000 in your browser.
"""

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from rag import answer_question

app = FastAPI(title="CyberAware Cameroon", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    history: Optional[List[dict]] = None


class SourceMeta(BaseModel):
    source_file: Optional[str] = None
    topic: Optional[str] = None
    language: Optional[str] = None
    source_url: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceMeta]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    try:
        result = answer_question(request.message, language=request.language)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chatbot error: {e}")
    return ChatResponse(answer=result["answer"], sources=result["sources"])