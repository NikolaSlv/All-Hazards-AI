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

from app.services.catalog_generation.csv_cat import (
    load_csv_catalog,
    render_csv_catalog_summary,
)
from app.services.catalog_generation.script_cat import (
    load_script_catalog,
    render_script_catalog_summary,
)
from app.services.llm_loader import model, tokenizer

# ─────────────────────────── Logging ──────────────────────────────────────
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

# ───────────────────── Prompt template ────────────────────────────────────
PROMPT_BODY = """
You are a *document-retrieval* and *execution* assistant.

Allowed targets:
- **CSV** files inside the `data/` folder,
- **Python scripts** inside `user_data/` via shell execution.

**Important:** Always begin your output with the keyword `Response:` on its own line, then immediately follow with the JSON block.

Return *EXACTLY ONE* JSON object whose ONLY key is "source_queries". Schema:

{{
  "source_queries": [
    {{
      "source_type": "<'csv' or 'shell'>",
      "file_path": "<path/to/file>"
    }}
  ]
}}

No extra keys, no prose - just the JSON block.

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

    # 1) Build catalog summaries
    try:
        csv_cat = load_csv_catalog()
        csv_summary = render_csv_catalog_summary(csv_cat)
    except Exception as exc:
        logger.warning("CSV catalog load failed: %s", exc)
        csv_summary = "WARNING: CSV catalog unavailable."

    try:
        script_cat = load_script_catalog()
        script_summary = render_script_catalog_summary(script_cat)
    except Exception as exc:
        logger.warning("Script catalog load failed: %s", exc)
        script_summary = "WARNING: script catalog unavailable."

    # 2) Compose full prompt
    full_prompt = "\n\n".join([
        csv_summary,
        script_summary,
        PROMPT_BODY.format(question=question),
    ])
    logger.debug("── Prompt to LLM ──\n%s\n── end prompt ──", full_prompt)

    # 3) Tokenize & generate
    inp = tokenizer(full_prompt, return_tensors="pt").to(model.device)
    t0 = time.time()
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
    logger.info("Generation %.2f s", time.time() - t0)

    # 4) Decode full output
    raw_full = tokenizer.decode(out_ids[0], skip_special_tokens=True).strip()
    logger.debug("LLM raw full output:\n%s", raw_full)

    # 5) Strip everything through the first Response→JSON marker
    marker = re.compile(
        r"Response\s*:\s*\{\s*\"source_queries\"\s*:\s*\[\s*\{",
        re.IGNORECASE | re.DOTALL,
    )
    m = marker.search(raw_full)
    if m:
        start = raw_full.find("{", m.start())
        raw_after = raw_full[start:]
        logger.debug("After slicing at custom marker:\n%s", raw_after)
    else:
        raw_after = raw_full

    # 6) Extract only the first JSON block
    try:
        json_block = _first_json(raw_after)
        logger.debug("Extracted JSON block:\n%s", json_block)
    except ValueError as err:
        logger.error("JSON extraction failed: %s", err)
        raise RuntimeError("Planner returned malformed or missing JSON") from err

    # 7) Parse & normalize
    plan_obj = json.loads(json_block)
    if "source_queries" not in plan_obj and plan_obj.get("source_type") == "file":
        plan_obj = {"source_queries": [plan_obj]}

    logger.info(
        "Planner produced %d file-query(ies)",
        len(plan_obj.get("source_queries", [])),
    )
    logger.debug("Final plan_obj: %s", plan_obj)

    return plan_obj
