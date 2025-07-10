#!/usr/bin/env python
"""
Dual FAISS stores: one for CSV rows, one for PDF chunks.

APIs
----
search_rows(question, csv_path, k=8)          → [row_idx, …]           # CSV index
search_rows_multi(question, csv_paths, k=8)   → {path: [row_idx,…],…}  # CSV index
search_pdf_chunks(question, pdf_path, k=8)    → [(page,chunk), …]      # PDF index
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple, Dict

import torch
import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from pypdf import PdfReader
from dateutil import parser as dp

logger = logging.getLogger("vector_index")

# ───────────────────────── config ─────────────────────────
DATA_DIR     = Path("data")
OUT_DIR      = Path(".vector_store")
CSV_DIR      = OUT_DIR / "csv"
PDF_DIR      = OUT_DIR / "pdf"
MODEL_NAME   = os.getenv("VEC_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# pick GPU if available
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device for embeddings: {DEVICE}")

for d in (CSV_DIR, PDF_DIR):
    d.mkdir(parents=True, exist_ok=True)

CSV_INDEX = CSV_DIR / "index.faiss"
CSV_META  = CSV_DIR / "meta.parquet"
PDF_INDEX = PDF_DIR / "index.faiss"
PDF_META  = PDF_DIR / "meta.parquet"

# ─────────────────────── helpers ─────────────────────────
def _norm(p: str | Path) -> str:
    return Path(p).as_posix().lower()

def _date_variants(raw: str) -> List[str]:
    try:
        dt = dp.parse(raw)
    except Exception:
        return []
    m, d, y = dt.month, dt.day, dt.year
    suf = {1:'st',2:'nd',3:'rd'}.get(d if d<20 else d%10, 'th')
    od  = f"{d}{suf}"
    return [
        f"{m}/{d}/{y}", dt.strftime("%m/%d/%Y"), f"{m}/{d}/{str(y)[2:]}",
        dt.strftime("%Y-%m-%d"),
        f"{dt.strftime('%B')} {d} {y}", f"{dt.strftime('%b')} {d} {y}",
        f"{dt.strftime('%B')} {od} {y}", f"{dt.strftime('%b')} {od} {y}",
    ]

_NUM_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

def _augment_question_with_dates(question: str) -> str:
    # 1) numeric date
    m = _NUM_DATE_RE.search(question)
    if m:
        raw = m.group(0)
    else:
        # 2) fuzzy parse fallback
        try:
            dt = dp.parse(question, fuzzy=True)
            raw = dt.strftime("%m/%d/%Y")
        except Exception:
            return question
    variants = _date_variants(raw)
    if not variants:
        return question
    return question + " | " + " | ".join(variants)

# ────────────────── CSV iteration ───────────────────────
def _iter_csv_items() -> Iterator[Tuple[str, str, int]]:
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path, dtype=str, engine="pyarrow", skiprows=1)
        except Exception:
            df = pd.read_csv(csv_path, dtype=str, engine="python", skiprows=1)
        npath = _norm(csv_path)
        for i in range(len(df)):
            key  = str(df.iloc[i, 0]).strip()
            # only embed the RowKey + its date variants
            text = " | ".join([f"RowKey={key}", *_date_variants(key)])
            yield text, npath, i

# ─────────────────── PDF iteration ────────────────────────
def _iter_pdf_items(max_chars: int = 2000) -> Iterator[Tuple[str, str, int]]:
    for pdf_path in sorted(DATA_DIR.glob("*.pdf")):
        npath  = _norm(pdf_path)
        reader = PdfReader(str(pdf_path))
        for pno, page in enumerate(reader.pages, start=1):
            txt = page.extract_text() or ""
            for ck, st in enumerate(range(0, len(txt), max_chars)):
                chunk      = txt[st:st+max_chars]
                snippet    = re.sub(r"\s+", " ", chunk).strip()
                embed_text = (
                    f"PDF={pdf_path.name} | page={pno} | chunk={ck} | {snippet}"
                )
                loc        = (pno << 16) | ck
                yield embed_text, npath, loc

# ─────────────────── build indexes ──────────────────────
def build_csv_index() -> None:
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    texts, paths, locs = [], [], []
    for t, p, l in tqdm(_iter_csv_items(), desc="Embedding CSV rows"):
        texts.append(t); paths.append(p); locs.append(l)
    if not texts:
        raise RuntimeError("No CSV rows to index")
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    faiss.write_index(idx, str(CSV_INDEX))
    pd.DataFrame({"path": paths, "loc": locs}).to_parquet(CSV_META)
    print(f"✅ CSV index saved to {CSV_DIR}")

def build_pdf_index() -> None:
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    texts, paths, locs = [], [], []
    for t, p, l in tqdm(_iter_pdf_items(), desc="Embedding PDF chunks"):
        texts.append(t); paths.append(p); locs.append(l)
    if not texts:
        raise RuntimeError("No PDF chunks to index")
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    faiss.write_index(idx, str(PDF_INDEX))
    pd.DataFrame({"path": paths, "loc": locs}).to_parquet(PDF_META)
    print(f"✅ PDF index saved to {PDF_DIR}")

def build_indexes() -> None:
    build_csv_index()
    build_pdf_index()

# ─────────────────── lazy loaders ────────────────────────
_csv_idx   = _csv_meta   = _csv_embed   = None
_pdf_idx   = _pdf_meta   = _pdf_embed   = None

def _lazy_csv() -> None:
    global _csv_idx, _csv_meta, _csv_embed
    if _csv_idx is not None:
        return
    if not CSV_INDEX.exists() or not CSV_META.exists():
        logger.warning("CSV store missing — rebuilding…")
        build_csv_index()
    _csv_idx   = faiss.read_index(str(CSV_INDEX))
    _csv_meta  = pd.read_parquet(CSV_META)
    _csv_embed = SentenceTransformer(MODEL_NAME, device=DEVICE)

def _lazy_pdf() -> None:
    global _pdf_idx, _pdf_meta, _pdf_embed
    if _pdf_idx is not None:
        return
    if not PDF_INDEX.exists() or not PDF_META.exists():
        logger.warning("PDF store missing — rebuilding…")
        build_pdf_index()
    _pdf_idx   = faiss.read_index(str(PDF_INDEX))
    _pdf_meta  = pd.read_parquet(PDF_META)
    _pdf_embed = SentenceTransformer(MODEL_NAME, device=DEVICE)

# ─────────────────── search APIs ────────────────────────
def search_rows(question: str, csv_path: str|Path, k: int=8) -> List[int]:
    _lazy_csv()
    aug_q = _augment_question_with_dates(question)
    qv, _ = _csv_embed.encode(
        [aug_q], return_numpy=True, normalize_embeddings=True
    ), None
    hits  = _csv_idx.search(qv, max(200, k))[1][0]

    results    = []
    abs_target = (PROJECT_ROOT / csv_path).resolve()
    for i in hits:
        if i < 0:
            break
        meta_path = (PROJECT_ROOT / _csv_meta.at[i, "path"]).resolve()
        if meta_path.samefile(abs_target):
            results.append(int(_csv_meta.at[i, "loc"]))
            if len(results) >= k:
                break
    return results

def search_rows_multi(
    question: str,
    csv_paths: Sequence[str|Path],
    k: int=8
) -> Dict[str, List[int]]:
    _lazy_csv()
    aug_q    = _augment_question_with_dates(question)
    qv       = _csv_embed.encode(
        [aug_q], return_numpy=True, normalize_embeddings=True
    )
    hits     = _csv_idx.search(qv, max(200, k))[1][0]
    abs_csv  = {
        str(p): (PROJECT_ROOT / Path(p)).resolve()
        for p in csv_paths
    }
    pm, done = {str(p): [] for p in csv_paths}, set()

    for i in hits:
        if i < 0:
            break
        meta_path = (PROJECT_ROOT / _csv_meta.at[i, "path"]).resolve()
        for orig_str, orig_abs in abs_csv.items():
            if meta_path.samefile(orig_abs) and orig_str not in done:
                pm[orig_str].append(int(_csv_meta.at[i, "loc"]))
                if len(pm[orig_str]) >= k:
                    done.add(orig_str)
        if len(done) == len(csv_paths):
            break

    return pm

def search_pdf_chunks(
    question: str,
    pdf_path: str|Path,
    k: int=8
) -> List[Tuple[int, int]]:
    _lazy_pdf()
    qv   = _pdf_embed.encode(
        [question], return_numpy=True, normalize_embeddings=True
    )
    hits = _pdf_idx.search(qv, max(200, k))[1][0]

    results    = []
    abs_target = (PROJECT_ROOT / pdf_path).resolve()
    for i in hits:
        if i < 0:
            break
        meta_path = (PROJECT_ROOT / _pdf_meta.at[i, "path"]).resolve()
        if meta_path.samefile(abs_target):
            loc = int(_pdf_meta.at[i, "loc"])
            results.append((loc >> 16, loc & 0xFFFF))
            if len(results) >= k:
                break
    return results

# ─────────────────────── CLI ─────────────────────────────
if __name__ == "__main__":
    build_indexes()
