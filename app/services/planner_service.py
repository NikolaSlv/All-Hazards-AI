#!/usr/bin/env python
"""
app/services/planner_service.py
────────────────────────────────────────────────────────────────────────
LLM-driven *Planner* that decides which data (CSV or shell) to retrieve.

✓ Talks to the external gRPC model-server (see start_llm.sh)
✓ FastAPI layer stays light-weight and hot-reloadable

Public API
──────────
    async def plan(question: str) -> dict
        → {"source_queries": [ … ]}
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List

import grpc
from transformers import GenerationConfig

# gRPC stubs (generated at repo root by start.sh)
import model_pb2
import model_pb2_grpc

from app.services.catalog_generation.csv_cat import (
    load_csv_catalog,
    render_csv_catalog_summary,
)
from app.services.catalog_generation.script_cat import (
    load_script_catalog,
    render_script_catalog_summary,
)

# ────────────────────────────── Logging ──────────────────────────────────
LOGLEVEL = getattr(
    logging,
    os.getenv("PLANNER_LOG_LEVEL", "INFO").upper(),
    logging.INFO,
)
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=LOGLEVEL,
)
logger = logging.getLogger("planner_service")

# ─────────────────── gRPC connection (singleton) ────────────────────────
_MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "localhost:50051")

_channel: grpc.aio.Channel | None = None
_stub: model_pb2_grpc.GeneratorStub | None = None


def _get_stub() -> model_pb2_grpc.GeneratorStub:
    """Create/re-use a single async stub."""
    global _channel, _stub
    if _stub is None:
        logger.info("Connecting to LLM micro-service @ %s …", _MODEL_SERVER_URL)
        _channel = grpc.aio.insecure_channel(_MODEL_SERVER_URL)
        _stub = model_pb2_grpc.GeneratorStub(_channel)
    return _stub


async def _generate_remote(prompt: str, cfg: GenerationConfig) -> str:
    """
    Call **StreamGenerate** and glue the streamed chunks together.
    """
    stub = _get_stub()
    req = model_pb2.GenerateRequest(
        prompt=prompt,
        max_new_tokens=cfg.max_new_tokens,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
    )

    pieces: List[str] = []
    async for chunk in stub.StreamGenerate(req):
        pieces.append(chunk.text)
    return "".join(pieces).strip()


# ───────────── Prompt template (braces escaped with {{ }}) ──────────────
PROMPT_BODY = """
You are a *document-retrieval* **and** *execution* assistant.

Allowed targets
– **CSV** files inside the `data/` folder
– **Python scripts** inside `user_data/` (via shell execution)

**Important** – always begin your answer with the keyword `Response:` on
its own line, then immediately output a single JSON object:

{{
  "source_queries": [
    {{
      "source_type": "<'csv' | 'shell'>",
      "file_path": "<relative/path/to/file>"
    }}
  ]
}}

No extra keys, no explanatory prose – *just* that JSON.

User question: "{question}"
""".strip()

_JSON_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL)


def _first_json(text: str) -> str:
    """Return the first JSON‐looking block in *text*."""
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("No JSON found in:\n" + text)
    return m.group(0)


# ───────────────────────────── Planner API ──────────────────────────────
async def plan(question: str) -> Dict[str, Any]:
    """
    Ask the LLM for a plan and return e.g.
        {"source_queries": [{"source_type":"csv", "file_path": …}, …]}
    """
    logger.info("Planning for: %s", question)

    # 1) Catalog summaries -------------------------------------------------
    try:
        csv_summary = render_csv_catalog_summary(load_csv_catalog())
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSV catalog unavailable: %s", exc)
        csv_summary = "WARNING: CSV catalog unavailable."

    try:
        script_summary = render_script_catalog_summary(load_script_catalog())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Script catalog unavailable: %s", exc)
        script_summary = "WARNING: script catalog unavailable."

    # 2) Compose prompt ----------------------------------------------------
    prompt = "\n\n".join(
        [csv_summary, script_summary, PROMPT_BODY.format(question=question)]
    )
    logger.debug("── Prompt sent to LLM ──\n%s\n── end prompt ──", prompt)

    # 3) Remote generation --------------------------------------------------
    cfg = GenerationConfig(max_new_tokens=160, temperature=0.0, top_p=1.0)
    t0 = time.time()
    raw = await _generate_remote(prompt, cfg)
    logger.info("LLM round-trip %.2f s", time.time() - t0)
    logger.debug("LLM raw output:\n%s", raw)

    # 4) Keep everything after the marker ----------------------------------
    marker = re.compile(
        r"Response\s*:\s*\{\s*\"source_queries\"\s*:\s*\[\s*\{",
        re.IGNORECASE | re.DOTALL,
    )
    m = marker.search(raw)
    after = raw[raw.find("{", m.start()) :] if m else raw

    # 5) Extract & parse JSON ----------------------------------------------
    json_block = _first_json(after)
    logger.debug("Extracted JSON block:\n%s", json_block)

    plan_obj: Dict[str, Any] = json.loads(json_block)
    if "source_queries" not in plan_obj and plan_obj.get("source_type"):
        # LLM returned a single object → wrap it in a list.
        plan_obj = {"source_queries": [plan_obj]}

    logger.info("Planner returned %d source-query(ies)", len(plan_obj["source_queries"]))
    logger.debug("Final plan_obj: %s", plan_obj)
    return plan_obj
