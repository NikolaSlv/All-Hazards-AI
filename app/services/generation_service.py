"""
Streams answer text token-by-token by delegating to the external LLM
gRPC micro-service.

The FastAPI layer stays light and can reload instantly, while the heavy
model lives in its own long-running process.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Dict, List, Any

import grpc
import model_pb2 as pb
import model_pb2_grpc as pbr          # generated stubs

from app.adapters.csv_adapter import format_csv_for_prompt
from app.adapters.shell_adapter import format_shell_for_prompt

logger = logging.getLogger("generation_service")

# ───────────────────────── Source-type   →  formatter ────────────────────
ADAPTERS: Dict[str, Callable[..., Any]] = {
    "csv":   format_csv_for_prompt,    # sync
    "shell": format_shell_for_prompt,  # async
}

# ─────────────────────── gRPC channel / stub (singleton) ──────────────────
_MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "localhost:50051")
_channel: grpc.aio.Channel | None = None
_stub:    pbr.GeneratorStub | None = None


async def _get_stub() -> pbr.GeneratorStub:
    global _channel, _stub
    if _stub is None:
        logger.info("Connecting to LLM micro-service @ %s …", _MODEL_SERVER_URL)
        _channel = grpc.aio.insecure_channel(_MODEL_SERVER_URL)
        _stub = pbr.GeneratorStub(_channel)
    return _stub


# ───────────────────────────── Prompt builder ────────────────────────────
async def _build_prompt(question: str, queries: List[Dict[str, str]]) -> str:
    """
    Builds the *user content* message that we will forward to the
    model-server.  The server itself will wrap this into the model’s
    chat-template, so no role tags are added here.
    """
    parts: List[str] = [question.strip(), ""]
    for q in queries:
        fmt = ADAPTERS.get(q.get("source_type"))
        if not fmt:
            continue
        snippet = await fmt(q) if asyncio.iscoroutinefunction(fmt) else fmt(q)
        parts.extend([snippet.strip(), ""])
    return "\n".join(parts).strip()   # single trailing newline


# ───────────────────────── Public streaming API ───────────────────────────
async def generate_answer_stream(
    question: str,
    source_queries: List[Dict[str, str]],
):
    """
    Async-generator that yields text chunks as soon as they arrive from the
    gRPC `StreamGenerate` endpoint.
    """
    user_content = await _build_prompt(question, source_queries)
    logger.debug("⇢ user-content to model-server:\n%s", user_content)

    stub = await _get_stub()

    MAX_NEW = int(os.getenv("MAX_NEW_TOKENS", "256"))

    req = pb.GenerateRequest(
        user_content   = user_content,   # <── changed
        max_new_tokens = MAX_NEW,
        temperature    = 0.7,
        top_p          = 0.9,
    )

    # `StreamGenerate` is an async iterator of `GenerateChunk`
    async for chunk in stub.StreamGenerate(req):
        yield chunk.text
