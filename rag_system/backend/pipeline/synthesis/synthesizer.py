from __future__ import annotations
"""
Stage 5: Final Synthesis

Model: gemma4:e4b (thinking ON for complex/root_cause, OFF for simple)
Streams tokens for responsive UI.
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

Question: {question}

Evidence:
{context}
"""


def synthesize(
    question:   str,
    context:    str,
    complexity: str = "moderate",
    intent:     str = "hybrid"
) -> str:
    """Generate final answer using gemma4:e4b with optional thinking mode."""
    use_thinking    = complexity == "complex" or intent in ("root_cause", "dependency", "hybrid")
    thinking_prefix = "/think" if use_thinking else "/no_think"

    from pipeline.llm_manager import chat_with_model
    
    # Qwen models don't need the explicit /think token
    messages = [{"role": "system", "content": "You are a senior software engineer analyzing a large codebase archive. Think step-by-step before answering."}] if use_thinking else []
    messages.append({
        "role": "user",
        "content": SYNTHESIS_PROMPT.format(
            thinking_prefix="",
            question=question,
            context=context
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
    intent:     str = "hybrid"
):
    """
    Generator version — yields token chunks for SSE streaming.
    Strips think blocks on the fly.
    """
    use_thinking    = complexity == "complex" or intent in ("root_cause", "dependency", "hybrid")
    thinking_prefix = "/think" if use_thinking else "/no_think"

    from pipeline.llm_manager import chat_with_model
    
    messages = [{"role": "system", "content": "You are a senior software engineer analyzing a large codebase archive. Think step-by-step before answering."}] if use_thinking else []
    messages.append({
        "role": "user",
        "content": SYNTHESIS_PROMPT.format(
            thinking_prefix="",
            question=question,
            context=context
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
