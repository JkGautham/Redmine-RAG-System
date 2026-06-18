"""
Stage 1: Preprocessor + Router

Model: gemma4:e4b (always resident)
One LLM call returns: normalized query, entities, temporal constraints,
intent classification, complexity, and the full retrieval plan.
"""

import json
import ollama
from config import PRIMARY_MODEL

PREPROCESS_PROMPT = """
You are a query parser for a Redmine software issue tracker archive.
The archive contains 44,000 issues, 41,427 journal comments, 2,186 relations,
and 10,253 attachments spanning 20 years.

Parse the user query and return ONLY valid JSON. No markdown. No explanation.

Schema:
{
  "clean_query": "normalized question text",
  "entities": {
    "issue_ids": [int], // Extract ANY issue numbers like #44132 -> 44132, or "issue 44132" -> 44132, or "from 59 to 61" -> [59, 61]
    "users": [str],
    "versions": [str],
    "trackers": [str],
    "statuses": [str],
    "error_codes": [str],
    "commit_refs": [str]
  },
  "temporal": {
    "after": "YYYY-MM-DD or null",
    "before": "YYYY-MM-DD or null",
    "relative": "last week / last month / null"
  },
  "intent": "root_cause|dependency|timeline|similar|attachment|hybrid",
  "complexity": "simple|moderate|complex",
  "graph_operation": "none|find_blockers|find_blocked|find_related|find_duplicates|dependency_chain|shortest_path|all_paths|ego_network|common_ancestors|impact_analysis|root_cause_chain|subgraph_summary|bidirectional_search|dynamic",
  "needs_attachments": true|false,
  "retrieval_plan": ["chroma_vector", "chroma_filter", "graph_operation",
                     "get_journals", "get_attachments", "html_fallback"]
}

Intent definitions:
- root_cause        -> "Why was X broken/fixed/delayed?"
- dependency        -> "What blocked/depends on X?"
- timeline          -> "How did X evolve over time?"
- similar           -> "Find related/duplicate bugs"
- attachment        -> "What does the file/screenshot in X show?"
- hybrid            -> Two or more of the above combined

Graph Operations:
- Select 'none' if no graph traversal is needed (e.g. plain text search, simple lookups).
- Level 1 (single-entity): find_blockers, find_blocked, find_related, find_duplicates
- Level 2 (two-entity): dependency_chain, shortest_path (e.g. from X to Y), all_paths, ego_network, bidirectional_search
- Level 3 (analytical): common_ancestors (e.g. what do X and Y have in common), impact_analysis, root_cause_chain, subgraph_summary
- Select 'dynamic' when:
  * The query involves cross-entity traversal (Issue→User, Issue→Project, etc.)
  * Examples: "issues by the same author", "latest issue raised by the reporter of #X",
    "all bugs assigned to the same developer as #X", "projects that share contributors"
  * The query needs aggregation, sorting, or filtering across relationships
  * You are unsure which specific operation fits but graph traversal is clearly needed

Retrieval plan rules:
- Always include chroma_vector for semantic queries
- Include chroma_filter when issue_ids are explicitly mentioned
- Include graph_operation when graph_operation != "none"
- Include get_journals for root_cause, timeline, dependency
- Include get_attachments when needs_attachments=true
- Include html_fallback only for simple=true + specific issue ID queries
  where live accuracy matters more than speed

User query: {query}
"""


def preprocess(query: str) -> dict:
    """Parse and plan retrieval for the user query using gemma4:e4b."""
    from pipeline.llm_manager import chat_with_model
    response = chat_with_model(
        model=PRIMARY_MODEL,
        messages=[{"role": "user", "content": PREPROCESS_PROMPT.replace("{query}", query)}],
        options={
            "temperature": 0.0,
            "num_predict": 768,
            "num_ctx": 8000
        }
    )
    raw = response["message"]["content"].strip()
    # Strip any accidental markdown fences
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "clean_query": query,
            "entities": {"issue_ids": [], "users": [], "versions": [],
                         "trackers": [], "statuses": [], "error_codes": [], "commit_refs": []},
            "temporal": {"after": None, "before": None, "relative": None},
            "intent": "hybrid",
            "complexity": "moderate",
            "graph_operation": "none",
            "needs_attachments": False,
            "retrieval_plan": ["chroma_vector"]
        }

    # --- Regex fallback for bulletproof Issue ID extraction ---
    import re
    if "entities" not in parsed:
        parsed["entities"] = {}
    if "issue_ids" not in parsed["entities"]:
        parsed["entities"]["issue_ids"] = []

    # Phase 1: Extract numbers explicitly marked as issue IDs
    #   e.g.  #7239, issue 7239, issue #7239, bug 7239, ticket 7239
    explicit = re.findall(
        r'(?:#|(?:issue|bug|ticket)\s*#?\s*)(\d{1,6})\b',
        query, re.IGNORECASE
    )
    for m in explicit:
        val = int(m)
        if val not in parsed["entities"]["issue_ids"] and val > 0:
            parsed["entities"]["issue_ids"].append(val)

    # Phase 2: Extract from explicit range patterns — "from X to Y", "between X and Y"
    for pattern in [
        r'from\s+#?(\d{1,6})\s+to\s+#?(\d{1,6})',
        r'between\s+#?(\d{1,6})\s+and\s+#?(\d{1,6})',
    ]:
        for m in re.finditer(pattern, query, re.IGNORECASE):
            for g in m.groups():
                val = int(g)
                if val not in parsed["entities"]["issue_ids"] and val > 0:
                    parsed["entities"]["issue_ids"].append(val)

    # Also include any IDs the LLM extracted that regex missed (it may have
    # understood contextual references like "the parent of 7239")
    llm_ids = parsed.get("entities", {}).get("issue_ids", [])
    for val in llm_ids:
        if isinstance(val, int) and val > 0 and val not in parsed["entities"]["issue_ids"]:
            parsed["entities"]["issue_ids"].append(val)

    # --- Detect cross-entity queries that need dynamic Cypher ---
    # These queries traverse Issue→User, Issue→Project, etc.
    # and CANNOT be answered by ego-expand or shortest-path.
    _DYNAMIC_KEYWORDS = [
        r'same\s+(?:author|reporter|assignee|user|person|developer)',
        r'(?:latest|newest|oldest|recent|first|last)\s+(?:issue|bug|ticket)\s+(?:by|from|raised|reported|created|filed)',
        r'(?:raised|reported|created|filed|assigned)\s+by\s+(?:the\s+)?same',
        r'who\s+(?:also\s+)?(?:raised|reported|created|filed|assigned)',
        r'(?:issues?|bugs?|tickets?)\s+(?:by|from)\s+(?:the\s+)?(?:same|this)\s+(?:author|reporter|user|person)',
        r'all\s+(?:issues?|bugs?|tickets?)\s+(?:by|from|reported|raised)',
        r'other\s+(?:issues?|bugs?|tickets?)\s+(?:by|from)',
    ]
    ql = query.lower()
    needs_dynamic = any(re.search(p, ql) for p in _DYNAMIC_KEYWORDS)

    # --- Graph operation heuristics (only override if LLM said "none") ---
    llm_op = parsed.get("graph_operation", "none")
    ids = parsed["entities"]["issue_ids"]
    intent = parsed.get("intent", "hybrid")

    if needs_dynamic:
        # Cross-entity query — always use dynamic, regardless of LLM choice
        parsed["graph_operation"] = "dynamic"
    elif llm_op != "none":
        # LLM already chose a meaningful operation — respect it
        pass
    elif len(ids) >= 2:
        # 2+ explicit issue IDs and LLM said "none" — heuristic override
        if "common" in ql:
            parsed["graph_operation"] = "common_ancestors"
        elif any(kw in ql for kw in ("path", "connect", "between", "link", "relate")):
            parsed["graph_operation"] = "shortest_path"
        else:
            # Default for 2+ IDs: ego_network is safer than shortest_path
            # (shortest_path often finds nothing if issues aren't directly linked)
            parsed["graph_operation"] = "ego_network"
    elif ids and intent != "attachment":
        # Single issue ID (but NOT attachment-focused query), LLM said "none" — ego-expand is appropriate
        # For attachment queries, skip ego_network and just fetch attachments directly
        parsed["graph_operation"] = "ego_network"
    else:
        # attachment-focused query or LLM said "none" with no IDs — no graph needed
        parsed["graph_operation"] = "none"

    # --- Auto-update retrieval plan ---
    plan = parsed.setdefault("retrieval_plan", [])
    if ids:
        if "chroma_filter" not in plan:
            plan.append("chroma_filter")
    if parsed.get("graph_operation", "none") != "none":
        if "graph_operation" not in plan:
            plan.append("graph_operation")

    # --- Attachment extraction heuristic ---
    needs_att = parsed.get("needs_attachments", False)
    if not needs_att:
        att_keywords = [r'\bpatch\b', r'\battachments?\b', r'\bpng\b', r'\bimages?\b', r'\bfiles?\b', r'\bpdf\b']
        needs_att = any(re.search(p, ql) for p in att_keywords)
        if needs_att:
            parsed["needs_attachments"] = True

    if needs_att and "get_attachments" not in plan:
        plan.append("get_attachments")

    print(
        f"=== [Preprocessor] IDs={ids}, "
        f"graph_op={parsed.get('graph_operation')}, "
        f"needs_dynamic={needs_dynamic}, plan={plan} ==="
    )

    return parsed

