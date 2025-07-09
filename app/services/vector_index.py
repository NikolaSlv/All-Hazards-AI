#!/usr/bin/env python
"""
Light-weight FAISS index: one vector per CSV row, embedding
RowKey + *many* common date variants + column names.

Public API
----------
search_rows(question, csv_path, k=8)          → [row_idx, …]
search_rows_multi(question, csv_paths, k=8)   → {path: [row_idx, …], …}

2025-07-09 update ④
-------------------
* Expanded **_row_repr()** to embed six canonical spellings for each
  date (with and without leading zeros, ISO, month names, …).
* Everything else is behaviour-identical to the ③ release.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, Tuple

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

logger = logging.getLogger("vector_index")

# ───────────────────────────────────────── config ──────────────────────────────────────
DATA_DIR   = Path("data")
OUT_DIR    = Path(".vector_store")
MODEL_NAME = os.getenv("VEC_MODEL_NAME", "sentence-transformers/all-mpnet-base-v2")

OUT_DIR.mkdir(exist_ok=True)
INDEX_FILE = OUT_DIR / "index.faiss"
META_FILE  = OUT_DIR / "meta.parquet"

# ───────────────────────────────────── helpers ─────────────────────────────────────────
def _norm_path(p: str | Path) -> str:
    """Cheap, case-insensitive POSIX normalisation (fallback comparison)."""
    return Path(p).as_posix().lower()


def _same_file(a: str | Path, b: str | Path) -> bool:
    """True if *a* and *b* refer to the same file (symlinks handled)."""
    try:
        return Path(a).resolve().samefile(b)
    except FileNotFoundError:
        return _norm_path(a) == _norm_path(b)


# ── date helpers ─────────────────────────────────────────────────────────────
def _date_variants(raw: str) -> List[str]:
    """
    Return multiple spellings for a date string – makes numeric-only
    queries like “02/25/2023” match just as well as “Feb 25 2023”.
    """
    from dateutil import parser as dp

    try:
        dt = dp.parse(raw, dayfirst=False, yearfirst=False)
    except (ValueError, OverflowError):
        return []

    return [
        dt.strftime("%-m/%-d/%Y"),   # 2/5/2023
        dt.strftime("%m/%d/%Y"),     # 02/05/2023
        dt.strftime("%-m/%-d/%y"),   # 2/5/23
        dt.strftime("%Y-%m-%d"),     # 2023-02-05
        dt.strftime("%B %-d %Y"),    # February 5 2023
        dt.strftime("%b %-d %Y"),    # Feb 5 2023
    ]


def _row_repr(df: pd.DataFrame, row_idx: int) -> str:
    """Return the text embedded for one CSV row."""
    row_key = str(df.iloc[row_idx, 0]).strip()       # e.g. 3/16/2023
    parts   = [f"RowKey={row_key}", * _date_variants(row_key)]
    parts  += [f"Cols={', '.join(df.columns[:50])}"]
    return " | ".join(parts)


def _iter_rows() -> Iterator[Tuple[str, str, int]]:
    """Yield (text, csv_path, row_idx) for every row in DATA_DIR/*.csv."""
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        try:
            logger.debug("Reading %s via pyarrow", csv_path)
            df = pd.read_csv(csv_path, dtype=str, engine="pyarrow", skiprows=1)
        except Exception as e:                       # noqa: BLE001
            logger.debug("PyArrow failed for %s: %s → fallback", csv_path, e)
            df = pd.read_csv(csv_path, dtype=str, engine="python", skiprows=1)

        for i in range(len(df)):
            yield _row_repr(df, i), _norm_path(csv_path), i

# ─────────────────────────────────── build index ───────────────────────────────────────
def build_index() -> None:
    """(Re)create the FAISS index from every CSV file in DATA_DIR."""
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    texts, paths, rows = [], [], []
    for txt, path, ridx in tqdm(_iter_rows(), desc="Embedding rows"):
        texts.append(txt)
        paths.append(path)
        rows.append(ridx)

    if not texts:
        raise RuntimeError("No CSV rows found under data/")

    emb = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)

    faiss.write_index(index, str(INDEX_FILE))
    pd.DataFrame({"csv": paths, "row": rows, "text": texts}).to_parquet(META_FILE)
    print(f"✅  Saved {index.ntotal} vectors  →  {OUT_DIR}/")

# ─────────────────────────────────── search API ────────────────────────────────────────
_index = _meta = _embed_model = None


def _lazy_load() -> None:
    global _index, _meta, _embed_model
    if _index is None:
        _index       = faiss.read_index(str(INDEX_FILE))
        _meta        = pd.read_parquet(META_FILE)
        _embed_model = SentenceTransformer(MODEL_NAME, device="cpu")


def _faiss_hits(question: str, pool: int = 200) -> np.ndarray:
    """Return indices of the top *pool* FAISS vectors for *question*."""
    _lazy_load()
    q_emb = _embed_model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    _, I = _index.search(q_emb, pool)
    return I[0]


def search_rows(question: str, csv_path: str | Path, k: int = 8) -> List[int]:
    """Return *k* best matching row indices inside *csv_path*."""
    hits: List[int] = []
    for idx in _faiss_hits(question):
        if _same_file(_meta.iloc[idx]["csv"], csv_path):
            hits.append(int(_meta.iloc[idx]["row"]))
            if len(hits) >= k:
                break
    return hits


def search_rows_multi(
    question: str,
    csv_paths: Sequence[str | Path],
    k: int = 8,
) -> Dict[str, List[int]]:
    """
    Search *multiple* CSVs at once.

    Parameters
    ----------
    question   : the natural-language query
    csv_paths  : iterable of paths (relative or absolute)
    k          : max rows to return *per* file

    Returns
    -------
    {str(path): [row_idx, …], …}  (paths use original spelling)
    """
    # Prepare bookkeeping
    path_map: Dict[str, List[int]] = {p: [] for p in csv_paths}
    done: set[str | Path] = set()

    for idx in _faiss_hits(question):
        meta_path = _meta.iloc[idx]["csv"]
        for orig in csv_paths:
            if orig in done:                       # already satisfied k for that file
                continue
            if _same_file(meta_path, orig):
                path_map[orig].append(int(_meta.iloc[idx]["row"]))
                if len(path_map[orig]) >= k:
                    done.add(orig)
        if len(done) == len(csv_paths):            # all satisfied
            break

    return path_map

# ───────────────────────────────────── CLI ─────────────────────────────────────────────
if __name__ == "__main__":
    build_index()
