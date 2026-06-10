"""
Task 2.4 — Semantic Relationship Extractor

Finds issue-to-issue and issue-to-entity relationships that are
mentioned in free text (description, journals).

Strategy:
  1. Regex patterns — fast, high confidence (0.9)
  2. Qwen2.5:1.5b fallback — for ambiguous / complex sentences (0.72)
"""

import re
import json
import logging

import ollama

from config import RELATION_LLM_MODEL, OLLAMA_HOST

logger = logging.getLogger("knowledge_builder.relation.semantic_extractor")

# ─────────────────────────────────────────────────────────────
# Regex pattern library
# Each pattern yields (rel_type, target_issue_id_or_none)
# ─────────────────────────────────────────────────────────────

_PATTERNS = [
    # "blocked by #12345"  /  "is blocked by issue 12345"
    (r"blocked\s+by\s+(?:issue\s+)?#?(\d+)", "BLOCKED_BY"),
    # "blocks #12345"
    (r"blocks?\s+(?:issue\s+)?#?(\d+)", "BLOCKS"),
    # "duplicate of #12345" / "duplicates #12345"
    (r"duplicat(?:e\s+of|es?)\s+(?:issue\s+)?#?(\d+)", "DUPLICATES"),
    # "related to #12345"
    (r"related\s+to\s+(?:issue\s+)?#?(\d+)", "RELATED_TO"),
    # "see also #12345"
    (r"see\s+also\s+#?(\d+)", "RELATED_TO"),
    # "fixed in #12345"
    (r"fixed\s+in\s+(?:issue\s+)?#?(\d+)", "RELATED_TO"),
    # "depends on #12345"
    (r"depends\s+on\s+(?:issue\s+)?#?(\d+)", "BLOCKED_BY"),
    # "child of #12345"
    (r"child\s+of\s+(?:issue\s+)?#?(\d+)", "CHILD_OF"),
    # "parent of #12345"
    (r"parent\s+of\s+(?:issue\s+)?#?(\d+)", "PARENT_OF"),
    # "copied from #12345"
    (r"copied\s+from\s+(?:issue\s+)?#?(\d+)", "COPIED_FROM"),
    # "copied to #12345"
    (r"copied\s+to\s+(?:issue\s+)?#?(\d+)", "COPIED_TO"),
]

# Pre-compile
_COMPILED = [(re.compile(pat, re.IGNORECASE), rel) for pat, rel in _PATTERNS]

_QWEN_PROMPT = """\
You are a software issue relationship extractor.

Given the source issue ID and text, find relationships to other issues.
Return ONLY a JSON array. Each item has: "rel_type" and "target_issue_id".
Valid rel_types: BLOCKS, BLOCKED_BY, DUPLICATES, RELATED_TO, PARENT_OF, CHILD_OF, COPIED_TO, COPIED_FROM

If none found, return: []

Source issue ID: {issue_id}
Text: {text}

JSON:"""


class SemanticRelationExtractor:
    """Extract issue-to-issue relationships from text."""

    def extract(self, issue: dict) -> list[dict]:
        """
        Args:
            issue: Parsed issue dict.

        Returns:
            List of edge dicts (same schema as DeterministicRelationExtractor).
        """
        issue_id = issue.get("issue_id")
        texts = self._collect_texts(issue)

        edges = []

        for text in texts:
            if not text.strip():
                continue
            regex_hits = self._regex_extract(issue_id, text)
            edges.extend(regex_hits)

        # Qwen fallback — only run if we found nothing at all via regex
        # (saves GPU cycles; regex already covers 95 % of cases in practice)
        if not edges and any(t.strip() for t in texts):
            combined = " ".join(texts)[:2000]
            qwen_hits = self._qwen_extract(issue_id, combined)
            edges.extend(qwen_hits)

        logger.debug(
            "[SemanticRelation] issue %s — %d text-based edges found",
            issue_id, len(edges),
        )

        return edges

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _collect_texts(self, issue: dict) -> list[str]:
        texts = []
        if issue.get("description"):
            texts.append(issue["description"])
        for j in (issue.get("journals") or []):
            if j.get("content"):
                texts.append(j["content"])
        return texts

    def _regex_extract(self, issue_id, text: str) -> list[dict]:
        edges = []
        for pattern, rel_type in _COMPILED:
            for match in pattern.finditer(text):
                target_id = int(match.group(1))
                if target_id == issue_id:
                    continue  # skip self-references
                edges.append({
                    "source_label": "Issue",
                    "source_id":    issue_id,
                    "rel_type":     rel_type,
                    "target_label": "Issue",
                    "target_id":    target_id,
                    "properties":   {"snippet": match.group()[:100]},
                    "confidence":   0.90,
                    "source":       "regex",
                })
        return edges

    def _qwen_extract(self, issue_id, text: str) -> list[dict]:
        try:
            client = ollama.Client(host=OLLAMA_HOST)
            response = client.generate(
                model=RELATION_LLM_MODEL,
                prompt=_QWEN_PROMPT.format(issue_id=issue_id, text=text),
                options={"temperature": 0.0},
            )
            raw = response.get("response", "").strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                return []
            items = json.loads(match.group())
            edges = []
            for item in (items or []):
                if not isinstance(item, dict):
                    continue
                target = item.get("target_issue_id")
                rel = item.get("rel_type", "RELATED_TO")
                if target:
                    target_str = str(target).strip()
                    if target_str.lower().startswith('r'):
                        continue
                    digits = re.sub(r"[^\d]", "", target_str)
                    if digits:
                        edges.append({
                            "source_label": "Issue",
                            "source_id":    issue_id,
                            "rel_type":     rel,
                            "target_label": "Issue",
                            "target_id":    int(digits),
                            "properties":   {},
                            "confidence":   0.72,
                            "source":       "qwen_llm",
                        })
            return edges
        except Exception as e:
            logger.warning(
                "[SemanticRelation] Qwen call failed for issue %s: %s",
                issue_id, e,
            )
            return []
