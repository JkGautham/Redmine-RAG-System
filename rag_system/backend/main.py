from __future__ import annotations
"""
FastAPI Backend — RAG System

Endpoints:
  POST /ask           — Full pipeline, returns JSON answer
  GET  /ask/stream    — SSE streaming endpoint (token by token)
  GET  /health        — Health check (Ollama, Neo4j, ChromaDB)
"""

import asyncio
import time
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

app = FastAPI(
    title="Redmine GraphRAG API",
    description="5-stage GraphRAG pipeline over 44,000 Redmine issues",
    version="2.0.0"
)

# Allow Next.js frontend on localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    answer:      str
    parsed:      Optional[dict] = None
    fused_count: int            = 0
    elapsed_ms:  float          = 0.0
    error:       Optional[str]  = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

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


def _stream_synthesis(query: str, context: str, parsed: dict):
    from pipeline.synthesis.synthesizer import synthesize_stream
    return synthesize_stream(
        question   = query,
        context    = context,
        complexity = parsed.get("complexity", "moderate"),
        intent     = parsed.get("intent", "hybrid")
    )


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)


# ─── Dev entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
