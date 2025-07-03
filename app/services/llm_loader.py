#!/usr/bin/env python
"""
Loads the LLM once at process start and exposes:

    • model      – transformers.AutoModelForCausalLM
    • tokenizer  – transformers.AutoTokenizer

The loader automatically chooses the most suitable precision:

┌───────────────────────────────┬────────────────────────────────────┐
│ GPU(s) available?             │ Precision & strategy               │
├───────────────────────────────┼────────────────────────────────────┤
│ H100 / A100 / recent GPUs     │ bf16   (or fp16) sharded on GPUs   │
│ Any CUDA GPU + LLM_LOAD_MODE= │ fp16   (“fp16”)                    │
│                               │ bf16   (“bf16”)                    │
│                               │ 4-bit NF4 (“4bit”) via bitsandbytes│
│ No CUDA or mode = “cpu”       │ bfloat16 **on CPU** (slow)         │
└───────────────────────────────┴────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import os
import platform
import time

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    logging as hf_logging,
)

# ─────────────────────────── Config ────────────────────────────
MODEL_NAME = "meta-llama/Meta-Llama-3-70B-Instruct"
CACHE_DIR  = os.getenv("HF_CACHE_DIR", "app/model_cache")
HF_TOKEN   = os.getenv("HUGGINGFACE_HUB_TOKEN", None)
LOAD_MODE  = os.getenv("LLM_LOAD_MODE", "").lower().strip()     # "", fp16, bf16, 4bit, cpu

logger = logging.getLogger("llm_loader")
hf_logging.set_verbosity_info()
hf_logging.enable_progress_bar()

IS_WINDOWS = platform.system() == "Windows"
HAS_CUDA   = torch.cuda.is_available()
GPU_COUNT  = torch.cuda.device_count()

logger.info("CUDA available: %s  |  GPUs: %d  |  LOAD_MODE=%s",
            HAS_CUDA, GPU_COUNT, LOAD_MODE or "(auto)")

# 4-bit quant config (only used if LOAD_MODE == "4bit")
_BNB_CFG = BitsAndBytesConfig(
    load_in_4bit              = True,
    bnb_4bit_compute_dtype    = torch.float16,
    bnb_4bit_use_double_quant = True,
    bnb_4bit_quant_type       = "nf4",
)

# ─────────────────── Tokenizer (always fast) ───────────────────
t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME, cache_dir=CACHE_DIR, use_fast=True, use_auth_token=HF_TOKEN
)
logger.info("Tokenizer loaded in %.1f s", time.time() - t0)

# ───────────────────── Model loader helpers ────────────────────
def _load_bf16_fp16(dtype: torch.dtype) -> AutoModelForCausalLM:
    logger.info("Loading model in %s across %d GPU(s)…", dtype, GPU_COUNT)
    return AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        torch_dtype=dtype,
        device_map="auto",           # sharded across all visible GPUs
        use_auth_token=HF_TOKEN,
    )

def _load_4bit() -> AutoModelForCausalLM:
    logger.info("Loading 4-bit NF4 quantised model (bitsandbytes)…")
    return AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        device_map="auto",
        quantization_config=_BNB_CFG,
        use_auth_token=HF_TOKEN,
    )

def _load_cpu() -> AutoModelForCausalLM:
    logger.info("Loading model *on CPU* (bfloat16)…")
    return AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        device_map={"": "cpu"},
        torch_dtype=torch.bfloat16,
        use_auth_token=HF_TOKEN,
    )

# ───────────────────── Choose a strategy ───────────────────────
def _load_model() -> AutoModelForCausalLM:
    # 1) explicit override via env var
    if LOAD_MODE == "fp16":
        return _load_bf16_fp16(torch.float16)
    if LOAD_MODE == "bf16":
        return _load_bf16_fp16(torch.bfloat16)
    if LOAD_MODE == "4bit":
        return _load_4bit()
    if LOAD_MODE == "cpu":
        return _load_cpu()

    # 2) automatic
    if HAS_CUDA and GPU_COUNT:
        # Prefer bf16 on H100 / A100 (they support bf16 natively)
        return _load_bf16_fp16(torch.bfloat16)
    if HAS_CUDA:
        return _load_bf16_fp16(torch.float16)

    # 3) fallback – CPU
    return _load_cpu()

# ─────────────────────── Load once ─────────────────────────────
t0 = time.time()
model = _load_model()
logger.info("Model ready in %.1f s", time.time() - t0)
