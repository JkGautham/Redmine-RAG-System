from __future__ import annotations
"""
Stage 3: RRF Evidence Fusion

Pure Python — no LLM.
Merges results from ChromaDB vector search, ChromaDB metadata filter,
and Neo4j graph — all keyed on issue_id.
"""


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    id_field: str = "issue_id",
    k: int = 60
) -> list[dict]:
    """
    Standard RRF. Each list is a ranked result from one retrieval source.
    Higher RRF score = appeared near top of multiple source rankings.
    k=60 is the standard constant (reduces sensitivity to rank-1 dominance).
    """
    scores: dict    = {}
    doc_store: dict = {}

    for ranked_list in result_lists:
        for rank, doc in enumerate(ranked_list):
            doc_id = doc.get(id_field)
            if doc_id is None:
                continue
            if doc_id not in scores:
                scores[doc_id]    = 0.0
                doc_store[doc_id] = doc
            scores[doc_id] += 1.0 / (k + rank + 1)

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [
        {**doc_store[doc_id], "rrf_score": round(scores[doc_id], 6)}
        for doc_id in sorted_ids
    ]


def fuse_all_evidence(
    vector_results:    list[dict],
    filter_results:    list[dict],
    graph_results:     list[dict],
    graph_expand_data: dict | None = None
) -> dict:
    """
    Master fusion function.
    Returns fused_issues (RRF ranked) + graph_context (separate, structured).
    """
    # RRF over issue-level results
    fused_issues = reciprocal_rank_fusion(
        [l for l in [vector_results, filter_results, graph_results] if l],
        id_field="issue_id"
    )

    # Graph expansion data is kept separate — structural, not ranked
    graph_context = {}
    if graph_expand_data:
        graph_context = {
            "detail": graph_expand_data.get("detail", {}),
            "outgoing": graph_expand_data.get("outgoing", []),
            "incoming": graph_expand_data.get("incoming", []),
            "journals": graph_expand_data.get("journals", []),
            "entities": graph_expand_data.get("entities", []),
            "dynamic_query": graph_expand_data.get("dynamic_query", [])
        }

    return {
        "fused_issues":  fused_issues,
        "graph_context": graph_context
    }
