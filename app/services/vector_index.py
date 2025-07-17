#!/usr/bin/env python
"""
Dual FAISS stores: one for CSV rows, one for PDF chunks,
plus on-the-fly FAISS indexing/search for oversized script outputs.

APIs
----
  build_csv_index()
  build_pdf_index()
  build_script_output_index(txt_path: str)
  build_indexes()

  search_rows(question, csv_path, k=8) -> List[int]
  search_rows_multi(question, csv_paths, k=8) -> Dict[path, List[int]]
  search_pdf_chunks(question, pdf_path, k=8) -> List[(page, chunk)]
  search_script_chunks(question, txt_path, k=8) -> List[int]
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple, Dict, Union

import torch
import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from pypdf import PdfReader
from dateutil import parser as dp

logger = logging.getLogger("vector_index")
logger.setLevel(logging.INFO)

# ───────────────────────── Configuration ─────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
STORE_ROOT   = PROJECT_ROOT / ".vector_store"

CSV_DIR    = STORE_ROOT / "csv"
PDF_DIR    = STORE_ROOT / "pdf"
SCRIPT_DIR = STORE_ROOT / "script"

MODEL_NAME = os.getenv("VEC_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"

# Ensure store directories exist
for d in (CSV_DIR, PDF_DIR, SCRIPT_DIR):
    d.mkdir(parents=True, exist_ok=True)

CSV_INDEX    = CSV_DIR / "index.faiss"
CSV_META     = CSV_DIR / "meta.parquet"
PDF_INDEX    = PDF_DIR / "index.faiss"
PDF_META     = PDF_DIR / "meta.parquet"
SCRIPT_INDEX = SCRIPT_DIR / "index.faiss"
SCRIPT_META  = SCRIPT_DIR / "meta.parquet"

# ───────────────────── Helpers ────────────────────────────────
def _norm(p: Union[str, Path]) -> str:
    return Path(p).as_posix().lower()

def _date_variants(raw: str) -> List[str]:
    try:
        dt = dp.parse(raw)
    except Exception:
        return []
    y, m, d = dt.year, dt.month, dt.day
    suf = {1:'st',2:'nd',3:'rd'}.get(d if d<20 else d%10, 'th')
    od  = f"{d}{suf}"
    variants = [
        f"{m}/{d}/{y}", dt.strftime("%m/%d/%Y"), f"{m}/{d}/{str(y)[2:]}",
        dt.strftime("%Y-%m-%d"),
        f"{dt.strftime('%B')} {d} {y}", f"{dt.strftime('%b')} {d} {y}",
        f"{dt.strftime('%B')} {od} {y}", f"{dt.strftime('%b')} {od} {y}",
    ]
    return variants

_NUM_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

def _augment_question_with_dates(question: str) -> str:
    m = _NUM_DATE_RE.search(question)
    if m:
        raw = m.group(0)
    else:
        try:
            dt = dp.parse(question, fuzzy=True)
            raw = dt.strftime("%m/%d/%Y")
        except Exception:
            return question
    variants = _date_variants(raw)
    return question + " | " + " | ".join(variants) if variants else question

# ─────────────────── CSV iteration ────────────────────────────
def _iter_csv_items() -> Iterator[Tuple[str, str, int]]:
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path, dtype=str, engine="pyarrow", skiprows=1)
        except Exception:
            df = pd.read_csv(csv_path, dtype=str, engine="python", skiprows=1)
        npath = _norm(csv_path)
        for i, row in df.iterrows():
            key  = str(row.iloc[0]).strip()
            text = " | ".join([f"RowKey={key}", *_date_variants(key)])
            yield text, npath, i

# ─────────────────── PDF iteration ────────────────────────────
def _iter_pdf_items(max_chars: int = 2000) -> Iterator[Tuple[str, str, int]]:
    for pdf_path in sorted(DATA_DIR.glob("*.pdf")):
        npath  = _norm(pdf_path)
        reader = PdfReader(str(pdf_path))
        for pno, page in enumerate(reader.pages, start=1):
            txt = page.extract_text() or ""
            for ck, st in enumerate(range(0, len(txt), max_chars)):
                chunk   = txt[st : st + max_chars]
                snippet = re.sub(r"\s+", " ", chunk).strip()
                embed_text = f"PDF={pdf_path.name} | page={pno} | chunk={ck} | {snippet}"
                loc     = (pno << 16) | ck
                yield embed_text, npath, loc

# ──────────────────── Build indexes ───────────────────────────
def build_csv_index() -> None:
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    texts, paths, locs = [], [], []
    for t, p, l in tqdm(_iter_csv_items(), desc="Embedding CSV rows"):
        texts.append(t); paths.append(p); locs.append(l)
    if not texts:
        raise RuntimeError("No CSV rows found for embedding")
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    faiss.write_index(idx, str(CSV_INDEX))
    pd.DataFrame({"path": paths, "loc": locs}).to_parquet(CSV_META)
    logger.info("✅ CSV index saved to %s", CSV_DIR)

def build_pdf_index() -> None:
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    texts, paths, locs = [], [], []
    for t, p, l in tqdm(_iter_pdf_items(), desc="Embedding PDF chunks"):
        texts.append(t); paths.append(p); locs.append(l)
    if not texts:
        raise RuntimeError("No PDF chunks found for embedding")
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    faiss.write_index(idx, str(PDF_INDEX))
    pd.DataFrame({"path": paths, "loc": locs}).to_parquet(PDF_META)
    logger.info("✅ PDF index saved to %s", PDF_DIR)

def build_script_output_index(txt_path: str) -> None:
    """
    Chunk & embed a large script-output file, writing to
    SCRIPT_INDEX and SCRIPT_META for on-the-fly RAG.
    """
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)
    # safe read
    raw = Path(txt_path).read_text(encoding="utf-8", errors="replace")
    chunk_size = int(os.getenv("SCRIPT_CHUNK_SIZE", "1000"))
    texts, paths, locs = [], [], []
    for i in range(0, len(raw), chunk_size):
        chunk = raw[i : i + chunk_size]
        texts.append(chunk)
        paths.append(txt_path)
        locs.append(i)
    if not texts:
        logger.warning("No text to index for %s", txt_path)
        return
    emb = model.encode(
        texts, batch_size=32, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )
    idx = faiss.IndexFlatIP(emb.shape[1])
    idx.add(emb)
    faiss.write_index(idx, str(SCRIPT_INDEX))
    pd.DataFrame({"path": paths, "loc": locs}).to_parquet(SCRIPT_META)
    logger.info("✅ Script-output index saved to %s", SCRIPT_DIR)

def build_indexes() -> None:
    """
    Convenience: rebuild only the CSV and PDF stores.
    Script-output index is built on-demand via build_script_output_index().
    """
    build_csv_index()
    build_pdf_index()

# ─────────────────── Lazy loaders & Search APIs ─────────────────────
_csv_idx:      faiss.IndexFlatIP | None = None
_csv_meta:     pd.DataFrame       | None = None
_csv_embed:    SentenceTransformer| None = None

_pdf_idx:      faiss.IndexFlatIP  | None = None
_pdf_meta:     pd.DataFrame       | None = None
_pdf_embed:    SentenceTransformer| None = None

_script_idx:   faiss.IndexFlatIP  | None = None
_script_meta:  pd.DataFrame       | None = None
_script_embed: SentenceTransformer| None = None

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

def _lazy_script() -> None:
    global _script_idx, _script_meta, _script_embed
    if _script_idx is not None:
        return
    if not SCRIPT_INDEX.exists() or not SCRIPT_META.exists():
        logger.warning("Script store missing — run build_script_output_index(txt_path) first")
        return
    _script_idx   = faiss.read_index(str(SCRIPT_INDEX))
    _script_meta  = pd.read_parquet(SCRIPT_META)
    _script_embed = SentenceTransformer(MODEL_NAME, device=DEVICE)

def search_rows(
    question: str,
    csv_path: Union[str, Path],
    k: int = 8,
) -> List[int]:
    _lazy_csv()
    # augment question with date variants
    aug = _augment_question_with_dates(question)
    qv  = _csv_embed.encode(
        [aug], return_numpy=True, normalize_embeddings=True
    )
    # search top 200 then filter to k for this file
    hits = _csv_idx.search(qv, max(200, k))[1][0]
    results: List[int] = []
    target = (PROJECT_ROOT / csv_path).resolve()
    for i in hits:
        if i < 0:
            break
        path_i = (PROJECT_ROOT / _csv_meta.at[i, "path"]).resolve()
        if path_i.samefile(target):
            results.append(int(_csv_meta.at[i, "loc"]))
            if len(results) >= k:
                break
    return results

def search_rows_multi(
    question: str,
    csv_paths: Sequence[Union[str, Path]],
    k: int = 8,
) -> Dict[str, List[int]]:
    _lazy_csv()
    aug  = _augment_question_with_dates(question)
    qv   = _csv_embed.encode(
        [aug], return_numpy=True, normalize_embeddings=True
    )
    hits = _csv_idx.search(qv, max(200, k))[1][0]
    out: Dict[str, List[int]] = {str(p): [] for p in csv_paths}
    resolved = {str(p): (PROJECT_ROOT / p).resolve() for p in csv_paths}

    for i in hits:
        if i < 0:
            break
        meta_path = (PROJECT_ROOT / _csv_meta.at[i, "path"]).resolve()
        for orig, abs_path in resolved.items():
            if meta_path.samefile(abs_path) and len(out[orig]) < k:
                out[orig].append(int(_csv_meta.at[i, "loc"]))
    return out

def search_pdf_chunks(
    question: str,
    pdf_path: Union[str, Path],
    k: int = 8,
) -> List[Tuple[int, int]]:
    _lazy_pdf()
    qv   = _pdf_embed.encode(
        [question], return_numpy=True, normalize_embeddings=True
    )
    hits = _pdf_idx.search(qv, max(200, k))[1][0]
    results: List[Tuple[int, int]] = []
    target = (PROJECT_ROOT / pdf_path).resolve()
    for i in hits:
        if i < 0:
            break
        path_i = (PROJECT_ROOT / _pdf_meta.at[i, "path"]).resolve()
        if path_i.samefile(target):
            loc = int(_pdf_meta.at[i, "loc"])
            results.append((loc >> 16, loc & 0xFFFF))
            if len(results) >= k:
                break
    return results

def search_script_chunks(
    question: str,
    txt_path: Union[str, Path],
    k: int = 8,
) -> List[int]:
    _lazy_script()
    if _script_idx is None:
        return []
    qv   = _script_embed.encode(
        [question], return_numpy=True, normalize_embeddings=True
    )
    hits = _script_idx.search(qv, max(200, k))[1][0]
    results: List[int] = []
    target = Path(txt_path).resolve()
    for i in hits:
        if i < 0:
            break
        row = _script_meta.iloc[i]
        path_i = Path(row["path"]).resolve()
        if path_i.samefile(target):
            results.append(int(row["loc"]))
            if len(results) >= k:
                break
    return results

# ───────────────────────── CLI ───────────────────────────────
if __name__ == "__main__":
    build_indexes()
