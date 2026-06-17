from __future__ import annotations
"""
Stage 5: Final Synthesis

Model: qwen3:8b (thinking ON for complex/root_cause, OFF for simple)
Streams tokens for responsive UI.
Supports conversation history for contextual follow-ups.
"""

import ollama
from config import PRIMARY_MODEL

SYNTHESIS_PROMPT = """
{thinking_prefix}
You are an expert software engineering analyst with access to a 20-year
Redmine issue archive (44,000 issues, 41,427 discussions, 10,253 attachments).

Rules:
- Answer using ONLY the evidence provided below.
- Always cite issue IDs (e.g. "Issue #44132") when referencing specific items.
- If the evidence is insufficient, say so — do not guess or hallucinate.
- For root cause questions: explain the chain of events, not just the symptom.
- For dependency questions: trace the full blocking chain clearly.
- For timeline questions: present events in chronological order.
- If the user references prior conversation context, use it for continuity.

{conversation_context}

Question: {question}

Evidence:
{context}
"""


def _format_conversation_history(history: list[dict] | None) -> str:
    """Format prior conversation messages for the synthesis prompt."""
    if not history:
        return ""
    
    lines = ["--- Prior Conversation Context ---"]
    for msg in history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        # Truncate long prior messages to save context window
        content = msg["content"]
        if len(content) > 500:
            content = content[:500] + "…"
        lines.append(f"{role_label}: {content}")
    lines.append("--- End Prior Context ---\n")
    return "\n".join(lines)


def synthesize(
    question:   str,
    context:    str,
    complexity: str = "moderate",
    intent:     str = "hybrid",
    conversation_history: list[dict] | None = None
) -> str:
    """Generate final answer using primary model with optional thinking mode."""
    use_thinking    = complexity == "complex" or intent in ("root_cause", "dependency", "hybrid")
    thinking_prefix = "/think" if use_thinking else "/no_think"

    from pipeline.llm_manager import chat_with_model
    
    conv_context = _format_conversation_history(conversation_history)
    
    # Qwen models don't need the explicit /think token
    messages = [{"role": "system", "content": "You are a senior software engineer analyzing a large codebase archive. Think step-by-step before answering."}] if use_thinking else []
    messages.append({
        "role": "user",
        "content": SYNTHESIS_PROMPT.format(
            thinking_prefix="",
            question=question,
            context=context,
            conversation_context=conv_context
        )
    })
    
    response = chat_with_model(
        model=PRIMARY_MODEL,
        messages=messages,
        options={
            "temperature": 0.2,
            "num_predict": 4096,
            "num_ctx":     24000
        },
        stream=True
    )

    full_text = ""
    for chunk in response:
        full_text += chunk["message"]["content"]

    # Strip <think>...</think> block before returning to user
    if "<think>" in full_text and "</think>" in full_text:
        before = full_text.split("<think>")[0]
        after  = full_text.split("</think>")[-1]
        full_text = (before + after).strip()

    return full_text.strip()


def synthesize_stream(
    question:   str,
    context:    str,
    complexity: str = "moderate",
    intent:     str = "hybrid",
    conversation_history: list[dict] | None = None
):
    """
    Generator version — yields token chunks for SSE streaming.
    Strips think blocks on the fly.
    """
    use_thinking    = complexity == "complex" or intent in ("root_cause", "dependency", "hybrid")
    thinking_prefix = "/think" if use_thinking else "/no_think"

    from pipeline.llm_manager import chat_with_model
    
    conv_context = _format_conversation_history(conversation_history)
    
    messages = [{"role": "system", "content": "You are a senior software engineer analyzing a large codebase archive. Think step-by-step before answering."}] if use_thinking else []
    messages.append({
        "role": "user",
        "content": SYNTHESIS_PROMPT.format(
            thinking_prefix="",
            question=question,
            context=context,
            conversation_context=conv_context
        )
    })
    
    response = chat_with_model(
        model=PRIMARY_MODEL,
        messages=messages,
        options={
            "temperature": 0.2,
            "num_predict": 4096,
            "num_ctx":     24000
        },
        stream=True
    )

    in_think_block = False
    buffer         = ""

    for chunk in response:
        token = chunk["message"]["content"]
        buffer += token

        # Suppress <think>...</think> blocks
        if "<think>" in buffer:
            in_think_block = True
        if in_think_block:
            if "</think>" in buffer:
                after = buffer.split("</think>")[-1]
                in_think_block = False
                buffer = after
                if after:
                    yield after
            # Don't yield while inside think block
            continue

        yield buffer
        buffer = ""
