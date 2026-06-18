from __future__ import annotations
"""
LangGraph State Machine — Agent Orchestration

5-stage pipeline:
  preprocess → retrieve (parallel) → fuse → compress → synthesize
"""

import time
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from concurrent.futures import ThreadPoolExecutor


class AgentState(TypedDict):
    raw_query:       str

    # Stage 1 output
    parsed:          Optional[dict]

    # Stage 2 outputs
    vector_results:  Optional[list]
    filter_results:  Optional[list]
    graph_expand:    Optional[dict]
    journal_list:    Optional[list]
    attachment_data: Optional[list]
    html_data:       Optional[dict]

    # Stage 3 output
    fused:           Optional[dict]

    # Stage 4 output
    journal_summary: Optional[str]
    context_bundle:  Optional[str]

    # Stage 5 output
    answer:          Optional[str]
    error:           Optional[str]

    # Metadata
    elapsed_ms:      Optional[float]


# ── Node implementations ─────────────────────────────────────────────────────

def node_preprocess(state: AgentState) -> AgentState:
    from pipeline.preprocessor import preprocess
    print(f"=== [Pipeline] Preprocessing query: '{state['raw_query']}' ===")
    try:
        state["parsed"] = preprocess(state["raw_query"]) ## preprocess
    except Exception as e:
        state["error"]  = f"Preprocessor failed: {e}"
        state["parsed"] = {
            "clean_query": state["raw_query"],
            "entities": {"issue_ids": []},
            "intent": "hybrid",
            "complexity": "moderate",
            "graph_operation": "none",
            "needs_attachments": False,
            "retrieval_plan": ["chroma_vector"]
        }
    return state


def node_retrieve(state: AgentState) -> AgentState:
    """Runs all retrieval in parallel using threads."""
    from pipeline.retrieval.chroma_retrieval import (
        chroma_vector_search, chroma_filter_by_id, get_journals_for_issue,
        get_attachment_index
    )
    from pipeline.retrieval.graph_retrieval import graph_expand
    from pipeline.retrieval.attachment_processor import process_attachments_for_issue
    from pipeline.retrieval.html_fallback import fetch_issue_html

    parsed = state.get("parsed") or {}
    plan   = parsed.get("retrieval_plan", ["chroma_vector"])
    query  = parsed.get("clean_query", state["raw_query"])
    ids    = parsed.get("entities", {}).get("issue_ids", [])

    def run_vector():
        if "chroma_vector" in plan:
            print(f"=== [Pipeline] Accessing Chroma Vector Search for query: '{query}' ===")
            return chroma_vector_search(query, n_results=20)
        return []

    def run_filter():
        if "chroma_filter" in plan and ids:
            print(f"=== [Pipeline] Accessing Chroma Metadata Filter for IDs: {ids} ===")
            return chroma_filter_by_id(ids)
        return []

    def run_graph():
        op = parsed.get("graph_operation", "none")
        # Only fire graph retrieval when explicitly requested
        needs_graph = ("graph_operation" in plan) or (op != "none")
        if not needs_graph:
            return {}

        from pipeline.retrieval.graph_retrieval import (
            graph_expand, graph_shortest_path, graph_bidirectional_search,
            graph_common_ancestors, graph_query_dynamic
        )

        if op in ("shortest_path", "dependency_chain") and len(ids) >= 2:
            print(f"=== [Pipeline] Accessing Neo4j Graph (Shortest Path) for IDs: {ids[0]} to {ids[1]} ===")
            return graph_shortest_path(ids[0], ids[1])

        elif op == "bidirectional_search" and len(ids) >= 2:
            print(f"=== [Pipeline] Accessing Neo4j Graph (Bidirectional) for IDs: {ids[0]} to {ids[1]} ===")
            return graph_bidirectional_search(ids[0], ids[1])

        elif op == "common_ancestors" and len(ids) >= 2:
            print(f"=== [Pipeline] Accessing Neo4j Graph (Common Ancestors) for IDs: {ids[0]} and {ids[1]} ===")
            return graph_common_ancestors(ids[0], ids[1])

        elif op in ("ego_network", "find_blockers", "find_blocked", "find_related", "find_duplicates") and ids:
            print(f"=== [Pipeline] Accessing Neo4j Graph (Ego/Expand) for ID: {ids[0]} ===")
            merged = graph_expand(ids[0], depth=5)
            for extra_id in ids[1:]:
                extra = graph_expand(extra_id, depth=5)
                merged["outgoing"].extend(extra.get("outgoing", []))
                merged["incoming"].extend(extra.get("incoming", []))
                merged["journals"].extend(extra.get("journals", []))
                merged["entities"].extend(extra.get("entities", []))
            return merged

        elif op == "dynamic":
            print(f"=== [Pipeline] Accessing Neo4j Graph (Dynamic Query) for: '{query}' ===")
            return graph_query_dynamic(query)

        elif ids:
            # Fallback: issue IDs present but op is unrecognised — ego-expand
            print(f"=== [Pipeline] Accessing Neo4j Graph (Fallback Expand) for ID: {ids[0]} ===")
            merged = graph_expand(ids[0], depth=5)
            for extra_id in ids[1:]:
                extra = graph_expand(extra_id, depth=5)
                merged["outgoing"].extend(extra.get("outgoing", []))
                merged["incoming"].extend(extra.get("incoming", []))
                merged["journals"].extend(extra.get("journals", []))
                merged["entities"].extend(extra.get("entities", []))
            return merged

        else:
            # op != "none" but no IDs and not "dynamic" — run dynamic query on raw query text
            print(f"=== [Pipeline] Accessing Neo4j Graph (Dynamic Query fallback) for: '{query}' ===")
            return graph_query_dynamic(query)

    def run_journals():
        if "get_journals" in plan and ids:
            print(f"=== [Pipeline] Accessing Journals for ID: {ids[0]} ===")
            return get_journals_for_issue(ids[0])
        return []

    def run_attachments():
        if "get_attachments" in plan and ids:
            print(f"=== [Pipeline] Accessing Attachments for ID: {ids[0]} ===")
            # Try Chroma first (legacy)
            index = get_attachment_index(ids[0])
            results = process_attachments_for_issue(ids[0], index)
            
            # If Chroma had no results, fall back to Neo4j
            if not results:
                print(f"=== [Pipeline] Chroma had no attachments, falling back to Neo4j ===")
                from pipeline.retrieval.graph_retrieval import graph_get_attachments
                neo4j_attachments = graph_get_attachments(ids[0])
                if neo4j_attachments:
                    print(f"=== [Pipeline] Found {len(neo4j_attachments)} attachments in Neo4j ===")
                    results = process_attachments_for_issue(ids[0], neo4j_attachments)
            
            return results
        return []

    def run_html():
        if "html_fallback" in plan and ids:
            return fetch_issue_html(ids[0])
        return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_vec  = pool.submit(run_vector)
        f_flt  = pool.submit(run_filter)
        f_grph = pool.submit(run_graph)
        f_jnl  = pool.submit(run_journals)
        f_att  = pool.submit(run_attachments)
        f_html = pool.submit(run_html)

        state["vector_results"]  = f_vec.result()
        state["filter_results"]  = f_flt.result()
        state["graph_expand"]    = f_grph.result()
        state["journal_list"]    = f_jnl.result()
        state["attachment_data"] = f_att.result()
        state["html_data"]       = f_html.result()

    return state


def node_fuse(state: AgentState) -> AgentState:
    from pipeline.fusion.rrf import fuse_all_evidence
    print("=== [Pipeline] Fusing Evidence (RRF) ===")

    # Flatten graph node results → issue list for RRF
    graph_issues = []
    if state.get("graph_expand"):
        for r in state["graph_expand"].get("outgoing", []):
            graph_issues.append({
                "issue_id": r.get("related_id"),
                "subject":  r.get("subject", ""),
                "status":   r.get("status", ""),
                "vector_score": 0.7
            })
        for r in state["graph_expand"].get("incoming", []):
            graph_issues.append({
                "issue_id": r.get("related_id"),
                "subject":  r.get("subject", ""),
                "status":   r.get("status", ""),
                "vector_score": 0.75
            })
        for r in state["graph_expand"].get("dynamic_query", []):
            if "node_path" in r:
                for n_id in r["node_path"]:
                    if n_id:
                        graph_issues.append({"issue_id": n_id, "subject": "", "status": "", "vector_score": 0.8})
            if "node_path1" in r:
                for n_id in r.get("node_path1", []) + r.get("node_path2", []):
                    if n_id:
                        graph_issues.append({"issue_id": n_id, "subject": "", "status": "", "vector_score": 0.8})
            # Dynamic queries return issue records with many possible column aliases;
            # check all common ones so rows reach the RRF ranker.
            issue_id = (
                r.get("id") or r.get("issue_id") or r.get("issueId")
                or r.get("Issue.id") or r.get("common_node")
                or r.get("related_id") or r.get("relatedId")
                or r.get("other_id") or r.get("otherId")
                or r.get("blocker_id") or r.get("blockerId")
                or r.get("dup_id") or r.get("dupId")
                or r.get("latest_issue_id") or r.get("latestIssueId")
            )
            if issue_id:
                graph_issues.append({
                    "issue_id": issue_id,
                    "subject":  (
                        r.get("subject") or r.get("Issue.subject")
                        or r.get("latestSubject") or r.get("relatedSubject") or ""
                    ),
                    "status":   r.get("status") or r.get("Issue.status", ""),
                    "vector_score": 0.8
                })

    state["fused"] = fuse_all_evidence(
        graph_results     = graph_issues,
        graph_expand_data = state.get("graph_expand"),
        vector_results    = state.get("vector_results") or [],
        filter_results    = state.get("filter_results") or [],
    )
    return state


def node_compress(state: AgentState) -> AgentState:
    from pipeline.compression.compressor import (
        compress_journals, compress_attachment_text, build_context_bundle
    )

    # Merge journals from multiple sources
    journals = (state.get("journal_list") or
                state.get("graph_expand", {}).get("journals", []))
    journal_summary = compress_journals(journals)

    att_compressed = []
    for att in (state.get("attachment_data") or []):
        summary = ""
        if att.get("text") and not att.get("error"):
            summary = compress_attachment_text(
                att["filename"], att.get("type", "unknown"), att["text"]
            )
        att_compressed.append({**att, "text": summary})

    # Primary issue — prefer exact filter match, else top vector result
    filter_r = state.get("filter_results") or []
    vector_r = state.get("vector_results") or []
    primary  = filter_r[0] if filter_r else (vector_r[0] if vector_r else {})

    print("=== [Pipeline] Assembling Context Bundle for Synthesizer ===")
    
    fused = state.get("fused") or {"fused_issues": [], "graph_context": {}}

    state["journal_summary"] = journal_summary
    state["context_bundle"]  = build_context_bundle(
        primary_issue    = primary,
        graph_context    = fused["graph_context"],
        fused_issues     = fused["fused_issues"],
        journal_summary  = journal_summary,
        attachment_texts = att_compressed,
        html_fallback    = state.get("html_data")
    )
    return state


def node_synthesize(state: AgentState) -> AgentState:
    from pipeline.synthesis.synthesizer import synthesize
    parsed = state.get("parsed") or {}
    print(f"=== [Pipeline] Synthesizing Final Answer (Context Size: {len(state.get('context_bundle', ''))} chars) ===")
    state["answer"] = synthesize(
        question   = state["raw_query"],
        context    = state.get("context_bundle", ""),
        complexity = parsed.get("complexity", "moderate"),
        intent     = parsed.get("intent", "hybrid")
    )
    return state


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_agent() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("preprocess", node_preprocess)
    g.add_node("retrieve",   node_retrieve)
    g.add_node("fuse",       node_fuse)
    g.add_node("compress",   node_compress)
    g.add_node("synthesize", node_synthesize)

    g.set_entry_point("preprocess")
    g.add_edge("preprocess", "retrieve")
    g.add_edge("retrieve",   "fuse")
    g.add_edge("fuse",       "compress")
    g.add_edge("compress",   "synthesize")
    g.add_edge("synthesize", END)

    return g.compile()


# ── Entry point ───────────────────────────────────────────────────────────────

def ask(query: str) -> dict:
    """
    Run the full pipeline and return structured result.
    Returns: {answer, parsed, fused_count, elapsed_ms, error}
    """
    t0    = time.time()
    agent = build_agent()
    result = agent.invoke({"raw_query": query})
    elapsed = (time.time() - t0) * 1000

    fused = result.get("fused") or {}
    return {
        "answer":      result.get("answer") or result.get("error", "No answer produced."),
        "parsed":      result.get("parsed"),
        "fused_count": len(fused.get("fused_issues", [])),
        "elapsed_ms":  round(elapsed, 1),
        "error":       result.get("error")
    }
