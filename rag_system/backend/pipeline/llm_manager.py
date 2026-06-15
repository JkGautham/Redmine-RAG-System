from __future__ import annotations
import threading
import ollama

_current_model = None
_lock = threading.Lock()

def chat_with_model(model: str, messages: list, options: dict = None, stream: bool = False):
    """
    Centralized LLM caller that handles unloading the previous model 
    before loading a new one to prevent out-of-memory errors.
    """
    global _current_model
    
    with _lock:
        # If we are switching models, unload the old one first
        if _current_model and _current_model != model:
            print(f"=== [LLM] Unloading previous model: {_current_model} ===")
            try:
                # keep_alive=0 unloads it from memory
                ollama.generate(model=_current_model, keep_alive=0)
            except Exception as e:
                print(f"=== [LLM] Failed to unload {_current_model}: {e} ===")
        
        # Print that we are loading the requested model
        if _current_model != model:
            print(f"=== [LLM] Loading new model: {model} ===")
            _current_model = model
        else:
            print(f"=== [LLM] Using already loaded model: {model} ===")
            
        ctx_len = (options or {}).get("num_ctx", "default")
        print(f"=== [LLM] Executing chat request on {model} (context window: {ctx_len}) ===")

    # Call Ollama chat endpoint
    return ollama.chat(
        model=model,
        messages=messages,
        options=options or {},
        stream=stream,
        keep_alive="2m"
    )
