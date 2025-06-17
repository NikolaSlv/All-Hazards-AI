"""
app/services/planner_service.py
──────────────────────────────────────────────────────────────────────────
Meta-Llama-3-8B-Instruct “Planner” for the RAG demo.

• Reuses the model & tokenizer from llm_loader so that
  loading happens only once at startup.
• Exports: async def plan(question:str) -> dict
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict

from transformers import GenerationConfig

from app.services.catalog_service import load_catalog, render_catalog_summary
from app.services.llm_loader import model, tokenizer

# ─────────────────────────── Logging ──────────────────────────────────────
LOGLEVEL = getattr(logging, os.getenv("PLANNER_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=LOGLEVEL)
logger = logging.getLogger("planner_service")

# ───────────────────── Prompt template ────────────────────────────────────
PROMPT_BODY = """
You are a *document-retrieval* assistant. Allowed targets are **CSV** files inside the project's **data/** folder (listed above).

**Important:** Always begin your output with the keyword `Response:` on its own line, then immediately follow with the JSON block.

Return *EXACTLY ONE* JSON object whose ONLY key is "source_queries". Schema (braces doubled):

{{
  "source_queries": [
    {{
      "source_type": "<type of source, e.g. 'csv'>",
      "file_path": "<relative/path/to/file>"
    }}
  ]
}}

No extra keys, no prose — just the JSON block.

User question: "{question}"
""".strip()

# Regex to grab the first {...} block (even if nested braces)
_JSON_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL)

def _first_json(text: str) -> str:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("No JSON found in:\n" + text)
    return m.group(0)

# ───────────────────── Planner entrypoint ─────────────────────────────────
async def plan(question: str) -> Dict[str, Any]:
    logger.info("Planning: %s", question)

    # 1) Build prompt (with catalog summary)
    try:
        summary = render_catalog_summary(load_catalog())
    except Exception as exc:
        logger.warning("Catalog load failed: %s", exc)
        summary = "WARNING: catalog unavailable."

    prompt = f"{summary}\n\n{PROMPT_BODY.format(question=question)}"
    logger.debug("── Prompt to LLM ──\n%s\n── end prompt ──", prompt)

    # 2) Generate
    inp = tokenizer(prompt, return_tensors="pt").to(model.device)
    t_gen = time.time()
    out_ids = model.generate(
        **inp,
        generation_config=GenerationConfig(
            max_new_tokens=160,
            do_sample=False,
            temperature=0.0,
            top_p=1.0,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        ),
    )
    logger.info("Generation %.2f s", time.time() - t_gen)

    # 3) Decode full output
    raw_full = tokenizer.decode(out_ids[0], skip_special_tokens=True).strip()
    logger.debug("LLM raw full output:\n%s", raw_full)

    # 4) Strip everything through the first Response→JSON marker:
    marker_pattern = (
        r"Response\s*:\s*"
        r"\{\s*\"source_queries\"\s*:\s*\[\s*\{"
    )
    marker_re = re.compile(marker_pattern, re.IGNORECASE | re.DOTALL)

    m = marker_re.search(raw_full)
    if m:
        # find the first '{' after the match and slice there
        start = raw_full.find("{", m.start())
        raw_after = raw_full[start:]
        logger.debug("After slicing at custom marker:\n%s", raw_after)
    else:
        raw_after = raw_full

    # 5) Extract only the first JSON block
    try:
        json_block = _first_json(raw_after)
        logger.debug("Extracted JSON block:\n%s", json_block)
    except ValueError as err:
        logger.error("JSON extraction failed: %s", err)
        raise RuntimeError("Planner returned malformed or missing JSON") from err

    # 6) Parse & normalize
    plan_obj = json.loads(json_block)
    if "source_queries" not in plan_obj and plan_obj.get("source_type") == "file":
        plan_obj = {"source_queries": [plan_obj]}

    logger.info(
        "Planner produced %d file-query(ies)",
        len(plan_obj.get("source_queries", [])),
    )
    return plan_obj
