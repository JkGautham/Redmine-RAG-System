"""
Task 2.3 — Semantic Entity Extractor

Primary:   GLiNER (CPU, no VRAM needed)
Fallback:  Qwen2.5:1.5b via Ollama (only when GLiNER score < threshold)

Extracts technology/tool entities hidden in descriptions and journal content.
"""

import json
import logging
import re

import ollama

from config import (
    GLINER_MODEL,
    GLINER_THRESHOLD,
    GLINER_ENTITY_LABELS,
    ENTITY_LLM_MODEL,
    OLLAMA_HOST,
)

logger = logging.getLogger("knowledge_builder.entity.semantic_extractor")

# ─────────────────────────────────────────────────────────────
# GLiNER loader (lazy — only imported if package is available)
# ─────────────────────────────────────────────────────────────

_gliner_model = None
_gliner_available = False


def _load_gliner():
    global _gliner_model, _gliner_available
    if _gliner_available:
        return True
    try:
        from gliner import GLiNER
        logger.info("[SemanticExtractor] Loading GLiNER model: %s", GLINER_MODEL)
        _gliner_model = GLiNER.from_pretrained(GLINER_MODEL)
        _gliner_available = True
        logger.info("[SemanticExtractor] GLiNER ready")
        return True
    except Exception as e:
        logger.warning(
            "[SemanticExtractor] GLiNER not available (%s) — will use Qwen fallback only",
            e,
        )
        return False


# ─────────────────────────────────────────────────────────────
# Qwen fallback prompt
# ─────────────────────────────────────────────────────────────

_QWEN_PROMPT = """\
You are a software engineering entity extractor.

Extract technology entities from the following text.
Only extract: databases, programming languages, frameworks, operating systems, APIs, tools, libraries, configuration files, or version strings.

Return ONLY a JSON array. Each item must have exactly two keys: "entity" and "type".
Example: [{{"entity": "PostgreSQL", "type": "Database"}}]

If no entities found, return an empty array: []

Text:
{text}

JSON:"""


def _qwen_extract(text: str) -> list[dict]:
    """Call Qwen2.5:1.5b via Ollama to extract entities from text."""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.generate(
            model=ENTITY_LLM_MODEL,
            prompt=_QWEN_PROMPT.format(text=text[:2000]),
            options={"temperature": 0.0},
        )
        raw = response.get("response", "").strip()

        # Extract JSON array from response (model sometimes adds prose)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []

        entities = json.loads(match.group())
        if not isinstance(entities, list):
            return []

        result = []
        for item in entities:
            if isinstance(item, dict) and "entity" in item:
                result.append({
                    "name":       item["entity"],
                    "label":      "Entity",
                    "entity_type": item.get("type", "Unknown"),
                    "source":     "qwen_llm",
                    "confidence": 0.72,
                })
        return result

    except Exception as e:
        logger.warning("[SemanticExtractor] Qwen call failed: %s", e)
        return []


class SemanticEntityExtractor:
    """
    Extract entities from free text (description + journals).

    Strategy:
      1. Try GLiNER.
      2. For spans with score < threshold, fall back to Qwen.
      3. If GLiNER unavailable entirely, use Qwen for all text.
    """

    def __init__(self):
        self._gliner_loaded = _load_gliner()

    def extract(self, issue: dict) -> list[dict]:
        """
        Args:
            issue: Parsed issue dict.

        Returns:
            List of entity dicts with name, label, source, confidence.
        """
        texts = self._collect_texts(issue)

        if not texts:
            return []

        entities = []
        low_confidence_texts = []

        for text in texts:
            if not text.strip():
                continue

            if self._gliner_loaded and _gliner_model is not None:
                gliner_hits = self._run_gliner(text)
                high = [e for e in gliner_hits if e["confidence"] >= GLINER_THRESHOLD]
                low  = [t for e, t in zip(gliner_hits, [text] * len(gliner_hits))
                        if e["confidence"] < GLINER_THRESHOLD]

                entities.extend(high)

                if low:
                    low_confidence_texts.append(text)
            else:
                # No GLiNER — queue everything for Qwen
                low_confidence_texts.append(text)

        # Qwen fallback for low-confidence or GLiNER-unavailable texts
        if low_confidence_texts:
            combined = " ".join(low_confidence_texts)[:3000]
            qwen_hits = _qwen_extract(combined)
            entities.extend(qwen_hits)

        logger.debug(
            "[SemanticExtractor] issue %s — %d entities extracted from text",
            issue.get("issue_id"), len(entities),
        )

        return entities

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _collect_texts(self, issue: dict) -> list[str]:
        texts = []
        if issue.get("description"):
            texts.append(issue["description"])
        for journal in (issue.get("journals") or []):
            if journal.get("content"):
                texts.append(journal["content"])
        return texts

    def _run_gliner(self, text: str) -> list[dict]:
        try:
            predictions = _gliner_model.predict_entities(
                text[:1000],           # GLiNER small handles ~512 tokens
                GLINER_ENTITY_LABELS,
                threshold=0.0,         # Get all hits; we filter by threshold ourselves
            )
            result = []
            for pred in predictions:
                result.append({
                    "name":       pred["text"],
                    "label":      "Entity",
                    "entity_type": pred["label"],
                    "source":     "gliner",
                    "confidence": round(pred["score"], 4),
                })
            return result
        except Exception as e:
            logger.warning("[SemanticExtractor] GLiNER inference failed: %s", e)
            return []
