"""
app/services/llm_loader.py
──────────────────────────────────────────────────────────────────────────
Loads the Meta-Llama LLM and tokenizer on import so that
the model is initialized once when the server starts.
Exports:
    - model: AutoModelForCausalLM
    - tokenizer: AutoTokenizer
"""

import os
import platform
import time
import logging

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    logging as hf_logging,
)

logger = logging.getLogger("llm_loader")
hf_logging.set_verbosity_info()
hf_logging.enable_progress_bar()

MODEL_NAME = "meta-llama/Meta-Llama-3-8B-Instruct"
CACHE_DIR  = os.getenv("HF_CACHE_DIR", "app/model_cache")
HF_TOKEN   = os.getenv("HUGGINGFACE_HUB_TOKEN", None)

IS_WINDOWS = platform.system() == "Windows"
HAS_CUDA   = torch.cuda.is_available()

logger.info("CUDA available: %s  |  OS: %s", HAS_CUDA, platform.system())

_BNB_CFG = BitsAndBytesConfig(
    load_in_4bit              = True,
    bnb_4bit_compute_dtype    = torch.float16,
    bnb_4bit_use_double_quant = True,
    bnb_4bit_quant_type       = "nf4",
)

# ─────────────────────── Tokenizer ───────────────────────────────────────
_tok_start = time.time()
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    cache_dir=CACHE_DIR,
    use_fast=True,
    use_auth_token=HF_TOKEN,
)
logger.info("Tokenizer loaded (%.1f s)", time.time() - _tok_start)

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
        except Exception as exc:
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
        except Exception as exc:
            logger.warning("bitsandbytes unavailable (%s). Falling back to CPU.", exc)

    logger.info("Loading on CPU … this may be slow.")
    return AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        device_map={"": "cpu"},
        torch_dtype=torch.bfloat16,
        use_auth_token=HF_TOKEN,
    )

# ─────────────────────────── Load model ───────────────────────────────────
_model_start = time.time()
model = _load_model()
logger.info("Model ready in %.1f s", time.time() - _model_start)
