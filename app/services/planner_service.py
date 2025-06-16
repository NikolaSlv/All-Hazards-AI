"""
app/services/planner_service.py
──────────────────────────────────────────────────────────────────────────
Meta-Llama-3-8B-Instruct “Planner” for the RAG demo.

• Tries full-GPU (fp16) first.
• If that fails → 4-bit bitsandbytes off-load (Linux/WSL only).
• If that fails → plain CPU.

Exports:  async def plan(question:str) -> dict
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import platform
from typing import Any, Dict

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    GenerationConfig,
    BitsAndBytesConfig,
    logging as hf_logging,
)

from app.services.catalog_service import load_catalog, render_catalog_summary

# ─────────────────────────  Logging  ──────────────────────────────────────
LOGLEVEL = getattr(logging, os.getenv("PLANNER_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=LOGLEVEL)
logger = logging.getLogger("planner_service")

hf_logging.set_verbosity_info()
hf_logging.enable_progress_bar()

# ─────────────────── Model / HF settings ─────────────────────────────────
MODEL_NAME = "meta-llama/Meta-Llama-3-8B-Instruct"
CACHE_DIR  = os.getenv("HF_CACHE_DIR", "app/model_cache")
HF_TOKEN   = os.getenv("HUGGINGFACE_HUB_TOKEN")

IS_WINDOWS = platform.system() == "Windows"
HAS_CUDA   = torch.cuda.is_available()

logger.info("CUDA available: %s  |  OS: %s", HAS_CUDA, platform.system())

# 4-bit quant config
_BNB_CFG = BitsAndBytesConfig(
    load_in_4bit              = True,
    bnb_4bit_compute_dtype    = torch.float16,
    bnb_4bit_use_double_quant = True,
    bnb_4bit_quant_type       = "nf4",
)

# ─────────────────────── Tokenizer ───────────────────────────────────────
tok_t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME, cache_dir=CACHE_DIR, use_fast=True, use_auth_token=HF_TOKEN
)
logger.info("Tokenizer loaded (%.1f s)", time.time() - tok_t0)

# ──────────────────────── Model loader ────────────────────────────────────
def _load_model() -> AutoModelForCausalLM:
    if HAS_CUDA:
        try:
            logger.info("Attempting full-precision fp16 on GPU …")
            return AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                cache_dir=CACHE_DIR,
                torch_dtype=torch.float16,
                device_map="auto",
                use_auth_token=HF_TOKEN,
            )
        except (RuntimeError, OSError) as exc:
            logger.warning("Full-GPU load failed (%s). Falling back.", exc)

    if not IS_WINDOWS:
        try:
            import bitsandbytes  # noqa: F401
            logger.info("Trying 4-bit bitsandbytes off-load …")
            return AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                cache_dir=CACHE_DIR,
                device_map="auto",
                quantization_config=_BNB_CFG,
                use_auth_token=HF_TOKEN,
            )
        except (ImportError, OSError) as exc:
            logger.warning("bitsandbytes unavailable (%s). Falling back to CPU.", exc)

    logger.info("Loading on CPU … this may be slow.")
    return AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        device_map={"": "cpu"},
        torch_dtype=torch.bfloat16,
        use_auth_token=HF_TOKEN,
    )

logger.info("Loading model weights …")
t0 = time.time()
model = _load_model()
logger.info("Model ready in %.1f s", time.time() - t0)

# ───────────────────── Prompt template ────────────────────────────────────
PROMPT_BODY = """
You are a *document-retrieval* assistant.  Allowed targets are **CSV** files inside the project's **data/** folder (listed above).

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

    # 1) Build prompt
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

    # 4) Strip everything up through the first literal sequence:
    #    Response:  {  "source_queries":  [    {
    #    allowing any whitespace around punctuation & newlines
    marker_pattern = (
        r"Response\s*:\s*"
        r"\{\s*\"source_queries\"\s*:\s*\[\s*\{"
    )
    marker_re = re.compile(marker_pattern, re.IGNORECASE | re.DOTALL)

    m = marker_re.search(raw_full)
    if m:
        # start at the '{' of the JSON block (group 0 includes it)
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

    # 6) Parse and normalize
    plan_obj = json.loads(json_block)
    if "source_queries" not in plan_obj and plan_obj.get("source_type") == "file":
        plan_obj = {"source_queries": [plan_obj]}

    logger.info(
        "Planner produced %d file-query(ies)",
        len(plan_obj.get("source_queries", [])),
    )
    return plan_obj
