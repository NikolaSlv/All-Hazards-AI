#!/usr/bin/env python
"""
app/services/model_server.py
────────────────────────────────────────────────────────────────────────
gRPC micro-service that keeps Meta-Llama-3-8B resident in memory and
streams tokens back to callers.

• Proto  : proto/model.proto  (no package statement)
• Service: Generator.StreamGenerate (unary request → streamed chunks)

Start the server from the repo root with:

    ./start_llm.sh
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import grpc
from transformers import GenerationConfig, TextIteratorStreamer

# gRPC stubs generated into the project root
import model_pb2 as pb
import model_pb2_grpc as pbr  # type: ignore

# One-time heavy model import (lives inside the same repo)
from app.services.llm_loader import model, tokenizer  # noqa: E402

logger = logging.getLogger("model_server")
logging.basicConfig(level=logging.INFO)


# ───────────────────────────── Servicer ──────────────────────────────
class GeneratorServicer(pbr.GeneratorServicer):  # type: ignore
    """Implements the StreamGenerate RPC."""

    async def StreamGenerate(
        self,
        request: pb.GenerateRequest,
        context: grpc.aio.ServicerContext,  # noqa: D401
    ):
        prompt = request.prompt
        logger.info("⏩  Received request (%d chars)", len(prompt))

        # — Build streamer that yields tokens as they are decoded —
        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            decode_kwargs={"skip_special_tokens": True},
        )

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        # — Kick off generation in a background thread —
        def _run_generation() -> None:
            model.generate(
                **inputs,
                streamer=streamer,
                generation_config=GenerationConfig(
                    max_new_tokens=request.max_new_tokens or 256,
                    do_sample=True,
                    temperature=request.temperature or 0.7,
                    top_p=request.top_p or 0.9,
                    eos_token_id=tokenizer.eos_token_id,
                    pad_token_id=tokenizer.eos_token_id,
                ),
            )

        threading.Thread(target=_run_generation, daemon=True).start()

        # — Stream tokens back to the client —
        for token in streamer:
            yield pb.GenerateChunk(text=token)


# ───────────────────────────── Server ────────────────────────────────
async def serve() -> None:
    server = grpc.aio.server()
    pbr.add_GeneratorServicer_to_server(GeneratorServicer(), server)  # type: ignore
    listen_addr = "[::]:50051"
    server.add_insecure_port(listen_addr)
    logger.info("🚀  LLM gRPC server listening on %s", listen_addr)

    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    # Ensure we can `import model_pb2`, etc., even if executed directly
    root = Path(__file__).resolve().parents[2]
    import sys

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    asyncio.run(serve())
