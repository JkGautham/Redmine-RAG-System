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
- Select 'none' if no graph traversal is needed.
- Level 1: find_blockers, find_blocked, find_related, find_duplicates
- Level 2: dependency_chain, shortest_path (e.g. from X to Y), all_paths, ego_network, bidirectional_search
- Level 3: common_ancestors (e.g. what do X and Y have in common), impact_analysis, root_cause_chain, subgraph_summary
- Select 'dynamic' if you are unsure but traversal is needed.

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
            "num_ctx": 4096
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
        
    # Extract numbers following '#' or 'issue', or isolated numbers that look like issue IDs (1 to 6 digits)
    matches = re.findall(r'(?:#|issue\s+|from\s+|to\s+|and\s+|between\s+)?\b(\d{1,6})\b', query, re.IGNORECASE)
    for m in matches:
        val = int(m)
        if val not in parsed["entities"]["issue_ids"] and val > 0:
            parsed["entities"]["issue_ids"].append(val)
            
    # Ensure graph_operation is dynamic if not set but IDs are present
    if parsed["entities"]["issue_ids"] and len(parsed["entities"]["issue_ids"]) >= 2 and parsed.get("graph_operation", "none") == "none":
        # Heuristic for multiple IDs
        if "common" in query.lower():
            parsed["graph_operation"] = "common_ancestors"
        else:
            parsed["graph_operation"] = "shortest_path"
            
    # Auto-update retrieval plan if IDs are found
    if parsed["entities"]["issue_ids"]:
        if "chroma_filter" not in parsed.get("retrieval_plan", []):
            parsed.setdefault("retrieval_plan", []).append("chroma_filter")
        if parsed.get("graph_operation", "none") != "none" and "graph_operation" not in parsed.get("retrieval_plan", []):
            parsed["retrieval_plan"].append("graph_operation")
        elif "graph_operation" not in parsed.get("retrieval_plan", []):
            parsed["retrieval_plan"].append("graph_operation")
            if parsed.get("graph_operation", "none") == "none":
                parsed["graph_operation"] = "ego_network" # Fallback to ego_network instead of graph_expand
            
    return parsed
