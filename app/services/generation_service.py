"""
app/services/generation_service.py
────────────────────────────────────────────────────────────────────────
Streams answer text token-by-token from the LLM.

• Uses TextIteratorStreamer with timeout=None  → blocks until each token
  is available (no _queue.Empty on slow hardware).
• FlushEachToken stopping-criteria forces the streamer to emit immediately
  after every generation step.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Dict, List, Any

from transformers import (
    GenerationConfig,
    TextIteratorStreamer,
    StoppingCriteria,
    StoppingCriteriaList,
)

from app.adapters.csv_adapter import format_csv_for_prompt
from app.adapters.shell_adapter import format_shell_for_prompt
from app.services.llm_loader import model, tokenizer

logger = logging.getLogger("generation_service")

# ─────────────────────────  Source-type → formatter  ──────────────────────
ADAPTERS: Dict[str, Callable[..., Any]] = {
    "csv":   format_csv_for_prompt,   # synchronous
    "shell": format_shell_for_prompt, # async
}

# ───────────────────────────  Prompt builder  ─────────────────────────────
async def _build_prompt(question: str, queries: List[Dict[str, str]]) -> str:
    parts: List[str] = [question, ""]
    for q in queries:
        fmt = ADAPTERS.get(q.get("source_type"))
        if not fmt:
            continue
        snippet = (
            await fmt(q) if asyncio.iscoroutinefunction(fmt) else fmt(q)
        )
        parts.extend([snippet, ""])
    return "\n".join(parts)

# ───────────────────  Flush every token immediately  ──────────────────────
class FlushEachToken(StoppingCriteria):
    """Called after every decode step → streamer flushes each token."""
    def __call__(self, *_, **__) -> bool:  # noqa: D401
        return False  # never stop early

# ──────────────────────────  Public generator  ────────────────────────────
async def generate_answer_stream(
    question: str,
    source_queries: List[Dict[str, str]],
):
    """
    Async-generator that yields text chunks as soon as the model produces
    them.  Intended for WebSocket streaming.
    """
    prompt = await _build_prompt(question, source_queries)
    logger.debug("Full generation prompt:\n%s", prompt)

    # timeout=None  → block until queue has an item (no _queue.Empty)
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
        decode_kwargs={"skip_special_tokens": True},
        timeout=None,
    )

    gen_inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # run generation in a background thread so we can iterate over streamer
    threading.Thread(
        target=model.generate,
        kwargs=dict(
            **gen_inputs,
            streamer=streamer,
            stopping_criteria=StoppingCriteriaList([FlushEachToken()]),
            generation_config=GenerationConfig(
                max_new_tokens=256,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.eos_token_id,
            ),
        ),
        daemon=True,
    ).start()

    # Yield every decoded token / small chunk as soon as it arrives
    for chunk in streamer:
        logger.debug("Streaming token: %s", chunk)
        yield chunk
