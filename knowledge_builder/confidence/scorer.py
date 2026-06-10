"""
Task 2.5 — Confidence Scorer

Normalises and validates confidence scores attached to entity / edge dicts.
Does not modify source of truth — just clamps and logs outliers.
"""

import logging

logger = logging.getLogger("knowledge_builder.confidence.scorer")

# Default scores by extraction source
SOURCE_DEFAULTS = {
    "deterministic": 1.0,
    "json_field":    1.0,
    "custom_field":  1.0,
    "regex":         0.90,
    "gliner":        None,   # uses model's own score
    "qwen_llm":      0.72,
    "unknown":       0.60,
}


def score(items: list[dict]) -> list[dict]:
    """
    Attach / validate `confidence` on a list of entity or edge dicts.

    Args:
        items: List of entity or edge dicts.

    Returns:
        Same list with guaranteed `confidence` float in [0.0, 1.0].
    """
    result = []
    for item in items:
        src = item.get("source", "unknown")
        existing = item.get("confidence")

        if existing is not None:
            # Clamp to valid range
            clamped = max(0.0, min(1.0, float(existing)))
        else:
            clamped = SOURCE_DEFAULTS.get(src, SOURCE_DEFAULTS["unknown"])

        if clamped != existing:
            logger.debug(
                "[Scorer] Clamped confidence from %.4f → %.4f (source=%s)",
                existing or 0, clamped, src,
            )

        result.append({**item, "confidence": clamped})

    return result
