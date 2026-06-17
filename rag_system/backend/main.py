from __future__ import annotations
"""
FastAPI Backend — RAG System

Endpoints:
  POST /ask           — Full pipeline, returns JSON answer
  GET  /ask/stream    — SSE streaming endpoint (token by token)
  POST /ask/chat/stream — SSE streaming with conversation context
  POST /ocr           — Upload image/PDF for VL-model processing
  GET  /conversations — List all conversations
  POST /conversations — Create new conversation
  GET  /conversations/{id} — Get conversation with messages
  PUT  /conversations/{id} — Update conversation title
  DELETE /conversations/{id} — Delete conversation
  GET  /health        — Health check (Ollama, Neo4j, ChromaDB)
"""

import asyncio
import os
import time
import tempfile
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import chat_store

app = FastAPI(
    title="Redmine GraphRAG API",
    description="5-stage GraphRAG pipeline over 44,000 Redmine issues with chat interface",
    version="3.0.0"
)

# Allow Next.js frontend on localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images as static files
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


# ─── Request/Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str


class ChatQueryRequest(BaseModel):
    query: str
    conversation_id: str
    ocr_text: Optional[str] = None


class QueryResponse(BaseModel):
    answer:      str
    parsed:      Optional[dict] = None
    fused_count: int            = 0
    elapsed_ms:  float          = 0.0
    error:       Optional[str]  = None


class ConversationCreate(BaseModel):
    title: str = "New Chat"


class ConversationUpdate(BaseModel):
    title: str


# ─── OCR / VL-Model Endpoint ─────────────────────────────────────────────────

@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    """
    Process an uploaded image or PDF using VL model for content extraction.
    Falls back to pytesseract if VL model is unavailable.
    Returns: {"text": "...", "filename": "..."}
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save uploaded file to disk
    suffix = Path(file.filename).suffix.lower()
    safe_name = f"upload_{int(time.time())}_{file.filename}"
    save_path = UPLOAD_DIR / safe_name
    
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    loop = asyncio.get_event_loop()

    # Route by file type
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"):
        text = await loop.run_in_executor(None, _process_image_vl, str(save_path))
    elif suffix == ".pdf":
        text = await loop.run_in_executor(None, _process_pdf, str(save_path))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    return {
        "text": text,
        "filename": file.filename,
        "saved_as": safe_name
    }


def _process_image_vl(path: str) -> str:
    """
    Process image using Ollama VL model for rich content extraction.
    Falls back to pytesseract OCR if VL model is unavailable.
    """
    import ollama

    # Vision-language model name fragments to detect (ordered by preference)
    vl_model_keywords = [
        "gemma4:e2b",
    ]

    try:
        list_response = ollama.list()
        # SDK returns a ListResponse object with a .models attribute (list of Model objects)
        model_objects = getattr(list_response, "models", None) or list_response.get("models", [])
        available_names = []
        for m in model_objects:
            if hasattr(m, "model"):
                available_names.append(m.model)           # SDK Model object
            elif isinstance(m, dict):
                available_names.append(m.get("name") or m.get("model", ""))
            else:
                available_names.append(str(m))

        # Find first matching VL model
        selected_vl = None
        for keyword in vl_model_keywords:
            for avail in available_names:
                if keyword in avail.lower():
                    selected_vl = avail
                    break
            if selected_vl:
                break

        if selected_vl:
            print(f"=== [OCR] Using VL model: {selected_vl} ===")
            response = ollama.chat(
                model=selected_vl,
                messages=[{
                    "role": "user",
                    "content": (
                        "Analyze this image thoroughly. Extract ALL text content you can see. "
                        "Also describe any diagrams, charts, screenshots, UI elements, code snippets, "
                        "error messages, or technical content visible. Be comprehensive and precise."
                    ),
                    "images": [path]
                }],
                options={"temperature": 0.1, "num_predict": 2048}
            )
            msg = response["message"] if isinstance(response, dict) else response.message
            content = msg["content"] if isinstance(msg, dict) else msg.content
            return content.strip()
        else:
            print(f"=== [OCR] No VL model found among: {available_names} ===")
    except Exception as e:
        print(f"=== [OCR] VL model failed: {e}, falling back to pytesseract ===")

    # Fallback: pytesseract OCR
    try:
        from PIL import Image
        from pytesseract import image_to_string
        img = Image.open(path)
        w, h = img.size
        if w < 1000:
            scale = 1000 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return image_to_string(img, lang="eng").strip()
    except Exception as e:
        return f"[OCR failed: {e}]"


def _process_pdf(path: str) -> str:
    """Extract text from PDF using pdfplumber."""
    import pdfplumber
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
    return "\n\n".join(pages_text)


# ─── Conversation Endpoints ──────────────────────────────────────────────────

@app.get("/conversations")
async def list_conversations():
    """List all conversations."""
    return chat_store.list_conversations()


@app.post("/conversations")
async def create_conversation(req: ConversationCreate):
    """Create a new conversation."""
    return chat_store.create_conversation(req.title)


@app.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get a conversation with all its messages."""
    conv = chat_store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = chat_store.get_messages(conv_id)
    return {**conv, "messages": messages}


@app.put("/conversations/{conv_id}")
async def update_conversation(conv_id: str, req: ConversationUpdate):
    """Update conversation title."""
    if not chat_store.update_conversation_title(conv_id, req.title):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation and all its messages."""
    if not chat_store.delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


# ─── Original Endpoints ──────────────────────────────────────────────────────

@app.post("/ask", response_model=QueryResponse)
async def ask_endpoint(req: QueryRequest):
    """Run the full RAG pipeline and return a complete answer."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Run blocking pipeline in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_pipeline, req.query)
    return QueryResponse(**result)


@app.get("/ask/stream")
async def ask_stream_endpoint(query: str):
    """
    SSE streaming endpoint. Token chunks are sent as they are generated.
    Usage: GET /ask/stream?query=Why+was+issue+%23123+delayed
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_generator():
        loop = asyncio.get_event_loop()

        # Stage 1: preprocess (fast, ~1s)
        parsed = await loop.run_in_executor(None, _preprocess, query)
        yield {"event": "parsed", "data": _json(parsed)}

        # Stage 2: retrieve (parallel, ~2-5s)
        retrieval_state = await loop.run_in_executor(None, _retrieve, query, parsed)
        yield {"event": "retrieved", "data": _json({"fused_count": retrieval_state.get("fused_count", 0)})}

        # Stage 3+4: fuse + compress (fast, no LLM)
        context = await loop.run_in_executor(None, _fuse_compress, retrieval_state)
        yield {"event": "context_ready", "data": ""}

        # Stage 5: stream synthesis tokens
        for chunk in _stream_synthesis(query, context, parsed):
            yield {"event": "token", "data": chunk}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ─── Chat-Aware Streaming Endpoint ───────────────────────────────────────────

@app.post("/ask/chat/stream")
async def ask_chat_stream_endpoint(req: ChatQueryRequest):
    """
    SSE streaming endpoint with conversation context.
    Saves messages to SQLite and uses conversation history for follow-ups.

    Flow: Upload processed first → query augmented → RAG pipeline → stream response
    """
    if not req.query.strip() and not req.ocr_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Augment query with OCR text if present
    augmented_query = req.query
    if req.ocr_text:
        augmented_query = (
            f"{req.query}\n\n"
            f"[Attached document/image content]:\n{req.ocr_text}"
        )

    # Save user message — store the augmented query so history retains OCR/image context
    chat_store.add_message(
        conversation_id=req.conversation_id,
        role="user",
        content=augmented_query,   # store full augmented text (includes OCR) for history continuity
        ocr_text=req.ocr_text
    )

    # Auto-title from first message (use the user-visible query, not augmented)
    messages = chat_store.get_messages(req.conversation_id)
    user_messages = [m for m in messages if m["role"] == "user"]
    if len(user_messages) == 1:
        chat_store.auto_title_from_query(req.conversation_id, req.query)

    # Get conversation history for LLM synthesis context
    conv_history = chat_store.get_conversation_context(req.conversation_id, max_pairs=5)
    # Remove the last user message we just added (it's the current query)
    if conv_history and conv_history[-1]["role"] == "user":
        conv_history = conv_history[:-1]

    # Build a context-aware retrieval query for follow-up messages.
    # If the query is short and vague (likely a follow-up), prepend the last
    # user+assistant exchange so the vector search has enough topic context.
    retrieval_query = augmented_query
    if conv_history and len(req.query.split()) < 15:
        # Grab last user message and last assistant snippet as retrieval context
        prior_user = next(
            (m["content"] for m in reversed(conv_history) if m["role"] == "user"), ""
        )
        prior_assistant = next(
            (m["content"][:300] for m in reversed(conv_history) if m["role"] == "assistant"), ""
        )
        if prior_user:
            retrieval_query = (
                f"{prior_user}\n\n"
                f"[Follow-up]: {augmented_query}"
            )

    async def event_generator():
        loop = asyncio.get_event_loop()
        full_answer = []

        # Stage 1: preprocess (use the context-enriched retrieval query)
        parsed = await loop.run_in_executor(None, _preprocess, retrieval_query)
        yield {"event": "parsed", "data": _json(parsed)}

        # Stage 2: retrieve with context-aware query
        retrieval_state = await loop.run_in_executor(None, _retrieve, retrieval_query, parsed)
        yield {"event": "retrieved", "data": _json({"fused_count": retrieval_state.get("fused_count", 0)})}

        # Stage 3+4: fuse + compress
        context = await loop.run_in_executor(None, _fuse_compress, retrieval_state)
        yield {"event": "context_ready", "data": ""}

        # Stage 5: stream synthesis with full conversation history
        # Pass the original augmented_query (not retrieval_query) so the answer
        # is worded for the user's actual question
        for chunk in _stream_synthesis(augmented_query, context, parsed, conv_history):
            full_answer.append(chunk)
            yield {"event": "token", "data": chunk}

        # Save assistant message to database
        answer_text = "".join(full_answer)
        chat_store.add_message(
            conversation_id=req.conversation_id,
            role="assistant",
            content=answer_text,
            metadata={
                "parsed": parsed,
                "fused_count": retrieval_state.get("fused_count", 0)
            }
        )

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health_check():
    """Check connectivity to Ollama, Neo4j, and ChromaDB."""
    status = {"status": "ok", "services": {}}

    # Check Ollama
    try:
        import ollama
        from config import PRIMARY_MODEL
        models = ollama.list()
        model_names = [m["name"] for m in models.get("models", [])]
        status["services"]["ollama"] = {
            "status": "ok",
            "models_available": model_names,
            "primary_model_ready": any(PRIMARY_MODEL in m for m in model_names)
        }
    except Exception as e:
        status["services"]["ollama"] = {"status": "error", "error": str(e)}
        status["status"] = "degraded"

    # Check Neo4j
    try:
        from pipeline.retrieval.graph_retrieval import _get_driver
        driver = _get_driver()
        with driver.session() as s:
            s.run("RETURN 1")
        status["services"]["neo4j"] = {"status": "ok"}
    except Exception as e:
        status["services"]["neo4j"] = {"status": "error", "error": str(e)}
        status["status"] = "degraded"

    # Check ChromaDB
    try:
        from pipeline.retrieval.chroma_retrieval import _get_collection
        col = _get_collection()
        count = col.count()
        status["services"]["chromadb"] = {"status": "ok", "document_count": count}
    except Exception as e:
        status["services"]["chromadb"] = {"status": "error", "error": str(e)}
        status["status"] = "degraded"

    return status


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _run_pipeline(query: str) -> dict:
    from pipeline.agent import ask
    return ask(query)


def _preprocess(query: str) -> dict:
    from pipeline.preprocessor import preprocess
    try:
        return preprocess(query)
    except Exception:
        return {
            "clean_query": query,
            "entities": {"issue_ids": []},
            "intent": "hybrid",
            "complexity": "moderate",
            "retrieval_plan": ["chroma_vector"]
        }


def _retrieve(query: str, parsed: dict) -> dict:
    """Run parallel retrieval and fuse — returns state dict."""
    from pipeline.agent import AgentState, node_retrieve, node_fuse
    state: AgentState = {
        "raw_query": query,
        "parsed": parsed,
        "vector_results": None, "filter_results": None,
        "graph_expand": None, "journal_list": None,
        "attachment_data": None, "html_data": None,
        "fused": None, "journal_summary": None,
        "context_bundle": None, "answer": None, "error": None,
        "elapsed_ms": None
    }
    state = node_retrieve(state)
    state = node_fuse(state)
    fused = state.get("fused") or {}
    return {**state, "fused_count": len(fused.get("fused_issues", []))}


def _fuse_compress(state: dict) -> str:
    from pipeline.agent import node_compress
    state = node_compress(state)
    return state.get("context_bundle", "")


def _stream_synthesis(query: str, context: str, parsed: dict, conversation_history: list[dict] | None = None):
    from pipeline.synthesis.synthesizer import synthesize_stream
    return synthesize_stream(
        question   = query,
        context    = context,
        complexity = parsed.get("complexity", "moderate"),
        intent     = parsed.get("intent", "hybrid"),
        conversation_history = conversation_history
    )


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)


# ─── Dev entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
