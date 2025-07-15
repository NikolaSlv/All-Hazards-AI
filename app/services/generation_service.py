"""
Streams answers via your LLM gRPC micro-service.

Debugs construction of user‐content and injection of CSV / shell snippets.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Dict, List, Any

import grpc
import model_pb2 as pb
import model_pb2_grpc as pbr

from app.adapters.csv_adapter   import format_csv_for_prompt
from app.adapters.pdf_adapter   import format_pdf_for_prompt
from app.adapters.shell_adapter import format_shell_for_prompt

logger = logging.getLogger("generation_service")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ADAPTERS: Dict[str, Callable[..., Any]] = {
    # key  →   adapter function         expected positional args
    "csv":     format_csv_for_prompt,   # (question, query)
    "pdf":     format_pdf_for_prompt,   # (question, query)
    "script":  format_shell_for_prompt, # (query)
}

_MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "localhost:50051")
_channel: grpc.aio.Channel | None = None
_stub:    pbr.GeneratorStub | None = None

async def _get_stub() -> pbr.GeneratorStub:
    global _channel, _stub
    if _stub is None:
        logger.info("Connecting to LLM micro-service @ %s …", _MODEL_SERVER_URL)
        _channel = grpc.aio.insecure_channel(_MODEL_SERVER_URL)
        _stub    = pbr.GeneratorStub(_channel)
    return _stub

async def _build_prompt(question: str, queries: List[Dict[str, str]]) -> str:
    logger.debug("Building prompt for question=%r with %d source_queries", question, len(queries))
    parts = [question.strip(), ""]
    for q in queries:
        stype = q.get("source_type")
        fmt   = ADAPTERS.get(stype)
        if not fmt:
            logger.debug("No adapter for source_type=%r", stype)
            continue
        if stype in ("csv", "pdf"):
            snippet = fmt(question, q)
        else:
            snippet = await fmt(q) if asyncio.iscoroutinefunction(fmt) else fmt(q)
        logger.debug("Snippet for %s:\n%s", stype, snippet[:200].replace("\n", "\\n"))
        parts.extend([snippet.strip(), ""])
    prompt = "\n".join(parts).strip()
    logger.debug("Final built prompt (head 200 chars):\n%s", prompt[:200].replace("\n", "\\n"))
    return prompt

async def generate_answer_stream(
    question: str,
    source_queries: List[Dict[str, str]],
):
    user_content = await _build_prompt(question, source_queries)
    logger.debug("⇢ user_content sent to model-server:\n%s", user_content)

    stub = await _get_stub()
    MAX_NEW = int(os.getenv("MAX_NEW_TOKENS", "256"))

    req = pb.GenerateRequest(
        user_content   = user_content,
        max_new_tokens = MAX_NEW,
        temperature    = 0.7,
        top_p          = 0.9,
    )

    logger.debug("Streaming from gRPC…")
    async for token in stub.StreamGenerate(req):
        # logger.debug("← token: %r", token.text)
        yield token.text
