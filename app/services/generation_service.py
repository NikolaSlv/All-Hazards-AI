from __future__ import annotations
import asyncio, threading, logging
from typing import List, Dict

from transformers import GenerationConfig, TextIteratorStreamer

from app.adapters.csv_adapter import format_csv_for_prompt
from app.services.llm_loader import model, tokenizer

logger = logging.getLogger("generation_service")
ADAPTERS = {"csv": format_csv_for_prompt}


def _build_prompt(question: str, qs: List[Dict[str, str]]) -> str:
    parts = [question, ""]
    for q in qs:
        fmt = ADAPTERS.get(q.get("source_type"))
        if fmt:
            parts += [fmt(q), ""]
    return "\n".join(parts)


async def generate_answer_stream(question, source_queries):
    prompt = _build_prompt(question, source_queries)

    # log the full prompt
    logger.info("Full generation prompt:\n%s", prompt)

    # create a streamer that will buffer tokens as they arrive
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
        decode_kwargs={"skip_special_tokens": True},
    )

    # fire off the actual generation in the background
    threading.Thread(
        target=model.generate,
        kwargs=dict(
            **tokenizer(prompt, return_tensors="pt").to(model.device),
            streamer=streamer,
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

    # now yield each token (or small chunk) as soon as it arrives
    for chunk in streamer:
        yield chunk
