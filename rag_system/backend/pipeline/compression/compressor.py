from __future__ import annotations
"""
Stage 4: Context Assembly

Assembles raw context from retrieval stages into a large prompt bundle.
No intermediate LLM summarization is used here; the final synthesis model
is trusted to read the full context.
"""

def render_path(node_path: list, edge_path: list) -> str:
    """Renders an explicit graph path into a vertical textual chain."""
    if not node_path:
        return ""
    lines = [f"Issue {node_path[0]}"]
    for i in range(len(edge_path)):
        if i + 1 < len(node_path):
            lines.append(f"  ↓ {edge_path[i]}")
            lines.append(f"Issue {node_path[i+1]}")
    return "\n".join(lines)

def compress_journals(journals: list[dict], max_input_chars: int = 15000) -> str:
    """Concatenates journals without LLM summarization."""
    if not journals:
        return ""

    combined = "\n---\n".join(
        f"[{j.get('author', '?')} @ {j.get('created_on', j.get('ts', ''))}]\n"
        f"{j.get('note', j.get('content', ''))}"
        for j in journals
        if j.get("note", j.get("content", "")).strip()
    )
    if not combined.strip():
        return ""
    if len(combined) > max_input_chars:
        combined = combined[:max_input_chars] + "\n...[truncated]"

    return combined


def compress_attachment_text(filename: str, file_type: str, text: str, max_chars: int = 10000) -> str:
    """Passes through attachment text without LLM summarization."""
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]"
    return text


def build_context_bundle(
    primary_issue:     dict,
    fused_issues:      list[dict],
    graph_context:     dict,
    journal_summary:   str,
    attachment_texts:  list[dict],
    html_fallback:     dict | None,
    token_budget:      int = 24000  # Increased token budget for full details
) -> str:
    """
    Assembles the final context string for synthesis.
    """
    char_budget = token_budget * 4
    parts = []

    # 1. Primary issue details (prioritize graph detail if available, else primary)
    graph_detail = graph_context.get("detail", {})
    src = html_fallback or primary_issue
    
    issue_id = graph_detail.get("id") or src.get("issue_id") or src.get("id", "?")
    if issue_id and str(issue_id) != "?":
        parts.append(
            f"## Primary Issue Context (Issue #{issue_id})\n"
            f"Subject: {graph_detail.get('subject') or src.get('subject', '?')}\n"
            f"Status: {graph_detail.get('status') or src.get('status', '?')} | "
            f"Tracker: {graph_detail.get('tracker') or src.get('tracker', '?')} | "
            f"Priority: {graph_detail.get('priority') or src.get('priority', '?')}\n"
            f"Reporter: {graph_detail.get('reporter') or src.get('author', '?')} | "
            f"Assignee: {graph_detail.get('assignee') or src.get('assignee', '?')}\n"
            f"Project: {graph_detail.get('project') or src.get('project', '?')}\n"
            f"Created: {graph_detail.get('created_on') or src.get('created_on', '?')}\n"
        )
        # Use HTML fallback description, graph description, or primary chroma text
        desc = src.get("description") or graph_detail.get("description") or src.get("text", "")
        if desc:
            parts.append(f"Description:\n{desc[:3000]}\n")

    # 2. Raw Journals
    if journal_summary:
        parts.append(f"## Discussion Thread (Journals)\n{journal_summary}\n")

    # 3. Graph structural context
    graph_parts = []
    
    all_graph_results = graph_context.get("incoming", []) + graph_context.get("outgoing", []) + graph_context.get("dynamic_query", [])
    
    for r in all_graph_results:
        if "node_path" in r and "edge_path" in r:
            rendered = render_path(r["node_path"], r["edge_path"])
            subject = r.get("subject", "")
            target_id = r.get('related_id') or r.get('dup_id') or r.get('blocker_id') or r.get('id')
            title = f"Chain involving Issue #{target_id} {subject}".strip() if target_id else "Graph Path"
            graph_parts.append(f"{title}:\n{rendered}\n")
        elif "node_path1" in r and "node_path2" in r:
            rendered1 = render_path(r["node_path1"], r["edge_path1"])
            rendered2 = render_path(r["node_path2"], r["edge_path2"])
            common_node = r.get('common_node')
            graph_parts.append(f"Common Ancestor (Issue #{common_node}):\nPath 1:\n{rendered1}\n\nPath 2:\n{rendered2}\n")
        elif "related_id" in r: # fallback
            graph_parts.append(f"Issue #{r['related_id']} ({r.get('status')}) - {r.get('subject')}")
            
    if graph_parts:
        parts.append("## Graph Structural Context (Paths & Chains)\n" + "\n---\n".join(graph_parts) + "\n")

    if graph_context.get("entities"):
        lines = [f"  - {e.get('type')}: {e.get('name')}" for e in graph_context["entities"]]
        parts.append("## Mentioned Entities (Commits, Users, Versions)\n" + "\n".join(lines) + "\n")

    # 4. Similar issues from vector search (Top 10 full details)
    if fused_issues:
        top = [f for f in fused_issues if str(f.get("issue_id")) != str(issue_id)][:10]
        if top:
            parts.append("## Related Issues Context (Full Details)\n")
            for r in top:
                parts.append(
                    f"Issue #{r.get('issue_id')} - {r.get('subject')}\n"
                    f"Status: {r.get('status', '?')} | Tracker: {r.get('tracker', '?')} | RRF Score: {r.get('rrf_score', 0):.4f}\n"
                    f"Details: {r.get('text', '')[:2500]}\n"
                    "---"
                )
            parts.append("\n")

    # 5. Attachments
    for att in attachment_texts:
        if att.get("text") and not att.get("error"):
            label = f"## Attachment: {att['filename']} ({att.get('type', 'unknown')})\n"
            parts.append(label + att["text"] + "\n")

    context = "\n".join(parts)
    if len(context) > char_budget:
        context = context[:char_budget] + "\n\n...[context truncated to fit token budget]"
    return context
