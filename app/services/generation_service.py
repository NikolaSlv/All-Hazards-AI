#!/usr/bin/env python
"""
Streams answers via your LLM gRPC micro-service.

Debugs construction of user‐content and injection of CSV / shell snippets,
with an on‐the‐fly RAG fallback for oversized script outputs.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Dict, List, Any
from pathlib import Path

import grpc
import model_pb2 as pb
import model_pb2_grpc as pbr

from app.adapters.csv_adapter   import format_csv_for_prompt
from app.adapters.pdf_adapter   import format_pdf_for_prompt
from app.adapters.shell_adapter import format_shell_for_prompt

import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer
import torch

logger = logging.getLogger("generation_service")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ─────────────────── Adapter mapping ───────────────────
ADAPTERS: Dict[str, Callable[..., Any]] = {
    "csv":    format_csv_for_prompt,
    "pdf":    format_pdf_for_prompt,
    "script": format_shell_for_prompt,
}

# ────────────────── gRPC stub setup ────────────────────
_MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "localhost:50051")
_channel: grpc.aio.Channel | None = None
_stub:    pbr.GeneratorStub | None  = None

async def _get_stub() -> pbr.GeneratorStub:
    global _channel, _stub
    if _stub is None:
        logger.info("Connecting to LLM micro-service @ %s …", _MODEL_SERVER_URL)
        _channel = grpc.aio.insecure_channel(_MODEL_SERVER_URL)
        _stub    = pbr.GeneratorStub(_channel)
    return _stub

# ─────────── Constants for RAG on script-output ───────────
BASE_DIR     = Path(__file__).resolve().parents[2]           # project root
VECTOR_STORE = BASE_DIR / ".vector_store" / "script"         # matches vector_index
SCRIPT_INDEX = VECTOR_STORE / "index.faiss"
SCRIPT_META  = VECTOR_STORE / "meta.parquet"
MODEL_NAME   = os.getenv("VEC_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"
TOP_K        = int(os.getenv("RAG_TOP_K", "8"))

def retrieve_script_chunks(txt_path: str, query: str, top_k: int = TOP_K) -> List[str]:
    """
    Load the FAISS index & metadata, embed the question,
    retrieve the top-k most similar 1 000-char chunks, and return them.
    """
    if not SCRIPT_INDEX.exists() or not SCRIPT_META.exists():
        logger.error("Script RAG store missing: %s or %s", SCRIPT_INDEX, SCRIPT_META)
        return []

    # load index + metadata
    idx  = faiss.read_index(str(SCRIPT_INDEX))
    meta = pd.read_parquet(str(SCRIPT_META))

    # embed the question
    embedder = SentenceTransformer(MODEL_NAME, device=DEVICE)
    q_emb    = embedder.encode([query], normalize_embeddings=True)
    _, I     = idx.search(q_emb, top_k)

    # pull raw text & re-chunk, run with replace to avoid crashes on bad bytes
    raw        = Path(txt_path).read_text(encoding="utf-8", errors="replace")
    chunk_size = 1000
    chunks: List[str] = []
    for i in I[0]:
        if i < 0 or i >= len(meta):
            continue
        loc = int(meta.iloc[i]["loc"])
        chunks.append(raw[loc : loc + chunk_size])
    return chunks

# ───────────────── build the LLM prompt ─────────────────
async def _build_prompt(
    question: str,
    queries: List[Dict[str, Any]],
) -> str:
    logger.debug("Building prompt for %r with %d source_queries", question, len(queries))
    parts: List[str] = [question.strip(), ""]

    for q in queries:
        stype = q.get("source_type")
        fmt   = ADAPTERS.get(stype)

        if not fmt:
            logger.debug("No adapter for source_type=%r, skipping", stype)
            continue

        # run the adapter
        if stype in ("csv", "pdf"):
            snippet = fmt(question, q)            # sync adapters
        else:  # "script"
            snippet = await fmt(q)               # async shell adapter

        # if run_shell spilled and indexed, we'll get a marker:
        if "__INDEXED_OUTPUT__:" in snippet:
            # pull the path out of the marker
            marker = snippet.split("__INDEXED_OUTPUT__:", 1)[1].strip()
            path   = marker.split()[0]
            logger.debug("Detected indexed marker, running RAG on %s", path)
            chunks = retrieve_script_chunks(path, question)
            # inline the real text chunks
            snippet = (
                "**Relevant Script-Output Chunks:**\n\n"
                + "\n\n".join(f"```\n{c}\n```" for c in chunks)
            )

        parts.extend([snippet.strip(), ""])

    prompt = "\n".join(parts).strip()
    logger.debug("Final built prompt (head 200 chars):\n%s", prompt[:200].replace("\n", "\\n"))
    return prompt

# ───────────────────── streaming answer ─────────────────────
async def generate_answer_stream(
    question: str,
    source_queries: List[Dict[str, str]],
):
    user_content = await _build_prompt(question, source_queries)
    logger.debug("⇢ user_content sent to model-server:\n%s", user_content)

    stub    = await _get_stub()
    MAX_NEW = int(os.getenv("MAX_NEW_TOKENS", "256"))

    req = pb.GenerateRequest(
        user_content   = user_content,
        max_new_tokens = MAX_NEW,
        temperature    = 0.7,
        top_p          = 0.9,
    )

    logger.debug("Streaming from gRPC…")
    async for token in stub.StreamGenerate(req):
        yield token.text
