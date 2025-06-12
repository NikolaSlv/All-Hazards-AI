"""
app/services/planner_service.py
──────────────────────────────────────────────────────────────────────────
Meta-Llama-3-70B-Instruct “Planner” for the RAG demo.

• Tries full-GPU (fp16) first.
• If that fails → 4-bit bitsandbytes off-load (Linux/WSL only).
• If that fails → plain CPU.

Exports:  async def plan(question:str) -> dict
"""

from __future__ import annotations

import json, logging, os, re, time, platform
from typing import Any, Dict

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    GenerationConfig,
    BitsAndBytesConfig,      # will be unused on Windows if bnb wheel absent
    logging as hf_logging,
)

from app.services.catalog_service import load_catalog, render_catalog_summary

# ─────────────────────────  Logging  ──────────────────────────────────────
LOGLEVEL = getattr(logging, os.getenv("PLANNER_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=LOGLEVEL)
logger = logging.getLogger("planner_service")

hf_logging.set_verbosity_info()
hf_logging.enable_progress_bar()

# ───────────────────────  Model / HF settings  ───────────────────────────
MODEL_NAME = "meta-llama/Meta-Llama-3-70B-Instruct"
CACHE_DIR  = os.getenv("HF_CACHE_DIR", "app/model_cache")
HF_TOKEN   = os.getenv("HUGGINGFACE_HUB_TOKEN")

IS_WINDOWS = platform.system() == "Windows"
HAS_CUDA   = torch.cuda.is_available()

logger.info("CUDA available: %s  |  OS: %s", HAS_CUDA, platform.system())

# 4-bit quant-config (will be used only if bitsandbytes import succeeds)
_BNB_CFG = BitsAndBytesConfig(
    load_in_4bit              = True,
    bnb_4bit_compute_dtype    = torch.float16,
    bnb_4bit_use_double_quant = True,
    bnb_4bit_quant_type       = "nf4",
)

# ───────────────────────  Tokeniser  ──────────────────────────────────────
tok_t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME, cache_dir=CACHE_DIR, use_fast=True, use_auth_token=HF_TOKEN
)
logger.info("Tokenizer loaded (%.1f s)", time.time() - tok_t0)

# ───────────────────────  Model loader  ───────────────────────────────────
def _load_model() -> AutoModelForCausalLM:
    # 1) full fp16 GPU
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
            logger.warning("Full-GPU load failed (%s).  Falling back.", exc)

    # 2) 4-bit bitsandbytes (Linux / WSL only)
    if not IS_WINDOWS:
        try:
            import bitsandbytes as _  # noqa: F401
            logger.info("Trying 4-bit bitsandbytes off-load …")
            return AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                cache_dir=CACHE_DIR,
                device_map="auto",
                quantization_config=_BNB_CFG,
                use_auth_token=HF_TOKEN,
            )
        except (ImportError, OSError) as exc:
            logger.warning("bitsandbytes unavailable (%s).  Falling back to CPU.", exc)

    # 3) plain CPU
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
for comp, dev in getattr(model, "hf_device_map", {}).items():
    logger.info("• %-28s → %s", comp, dev)

# ─────────────────────  Prompt template  ─────────────────────────────────
PROMPT_BODY = """
You are a *document-retrieval* assistant.  Allowed targets are **CSV/TXT**
files inside the project’s **data/** folder (listed above).

Return *EXACTLY ONE* JSON object whose ONLY key is "source_queries".
That key contains a list of 1-3 file queries.  Schema (braces doubled):

{{
  "source_queries": [
    {{
      "source_type": "file",
      "file_path": "<relative/path/to/file>",
      "start_line": 1,
      "end_line": 200
    }}
  ]
}}

No extra keys, no prose — just the JSON block.

User question: "{question}"
""".strip()

_JSON_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL)
def _first_json(text: str) -> str:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("No JSON found")
    return m.group(0)

# ─────────────────────  Planner entrypoint  ──────────────────────────────
async def plan(question: str) -> Dict[str, Any]:
    logger.info("Planning: %s", question)

    # catalog summary
    try:
        summary = render_catalog_summary(load_catalog())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalog load failed: %s", exc)
        summary = "WARNING: catalog unavailable."

    prompt = f"{summary}\n\n{PROMPT_BODY.format(question=question)}"
    logger.debug("── Prompt to LLM ──\n%s\n── end prompt ──", prompt)

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

    raw = tokenizer.decode(out_ids[0], skip_special_tokens=True).strip()
    logger.debug("LLM raw output:\n%s", raw)

    try:
        plan_obj: Dict[str, Any] = json.loads(_first_json(raw))
    except Exception as err:
        logger.error("JSON parse failure – raw output above.")
        raise RuntimeError(f"Planner returned malformed JSON: {err}") from err

    # auto-wrap naked dict
    if "source_queries" not in plan_obj and plan_obj.get("source_type") == "file":
        plan_obj = {"source_queries": [plan_obj]}

    logger.info("Planner produced %d file-query(ies)",
                len(plan_obj.get("source_queries", [])))
    return plan_obj
