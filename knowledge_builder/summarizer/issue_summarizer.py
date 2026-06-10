"""
Task 2.6 — Issue Summarizer

Generates a 2-3 sentence summary of each issue using Qwen2.5:1.5b via Ollama.
Summary is stored:
  - On the Issue node in Neo4j (property: summary)
  - As a parent chunk in ChromaDB (chunk_type: summary)
"""

import logging

import ollama

from config import SUMMARIZER_MODEL, OLLAMA_HOST, ENABLE_SUMMARIZATION

logger = logging.getLogger("knowledge_builder.summarizer")

_PROMPT_TEMPLATE = """\
You are a software engineering analyst summarizing a bug tracker issue.

Write a single concise paragraph (2-3 sentences max) summarizing the issue.
Include: what the problem is, what was investigated or changed, and the outcome.
Do NOT include issue IDs, dates, or names. Use present tense.

Issue details:
Tracker: {tracker}
Status:  {status}
Subject: {subject}
Description: {description}
Recent journal activity: {journals}

Summary:"""


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


class IssueSummarizer:
    """Generate issue summaries via Qwen2.5:1.5b."""

    def __init__(self):
        if ENABLE_SUMMARIZATION:
            self._client = ollama.Client(host=OLLAMA_HOST)
        else:
            self._client = None

    def summarize(self, issue: dict) -> str:
        """
        Generate a summary string for the issue.

        If summarization is disabled or Ollama fails, returns a
        fallback rule-based summary.

        Args:
            issue: Parsed issue dict.

        Returns:
            Summary string.
        """
        if not ENABLE_SUMMARIZATION or self._client is None:
            return self._fallback_summary(issue)

        try:
            journals_text = self._format_journals(issue.get("journals") or [])
            prompt = _PROMPT_TEMPLATE.format(
                tracker=issue.get("tracker", "Unknown"),
                status=issue.get("status", "Unknown"),
                subject=_truncate(issue.get("subject", ""), 200),
                description=_truncate(issue.get("description", ""), 800),
                journals=_truncate(journals_text, 600),
            )

            response = self._client.generate(
                model=SUMMARIZER_MODEL,
                prompt=prompt,
                options={"temperature": 0.3, "num_predict": 150},
            )

            summary = response.get("response", "").strip()

            if not summary:
                return self._fallback_summary(issue)

            logger.debug(
                "[Summarizer] issue %s — summary generated (%d chars)",
                issue.get("issue_id"), len(summary),
            )

            return summary

        except Exception as e:
            logger.warning(
                "[Summarizer] Ollama call failed for issue %s: %s — using fallback",
                issue.get("issue_id"), e,
            )
            return self._fallback_summary(issue)

    @staticmethod
    def _fallback_summary(issue: dict) -> str:
        """Rule-based summary when LLM is unavailable."""
        parts = [
            f"{issue.get('tracker', 'Issue')} #{issue.get('issue_id', '?')}:",
            issue.get("subject", "No subject"),
        ]
        if issue.get("status"):
            parts.append(f"[{issue['status']}]")
        if issue.get("description"):
            parts.append(_truncate(issue["description"], 200))
        return " ".join(parts)

    @staticmethod
    def _format_journals(journals: list) -> str:
        lines = []
        for j in journals[-5:]:   # Last 5 journal entries
            content = j.get("content", "")
            changes = j.get("changes", [])
            entry_parts = []
            if content:
                entry_parts.append(content[:200])
            if changes:
                entry_parts.append(" | ".join(changes[:3]))
            if entry_parts:
                lines.append("; ".join(entry_parts))
        return "\n".join(lines)
