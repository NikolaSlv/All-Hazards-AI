#!/usr/bin/env python
"""
CSV → prompt snippet adapter (header-aware, date-aware, resilient).
"""
from __future__ import annotations
import os, re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from dateutil import parser as dp

from app.services.vector_index import search_rows

MAX_ROWS = int(os.getenv("MAX_CSV_RETR_ROWS", "10"))
MAX_COLS = int(os.getenv("MAX_CSV_RETR_COLS", "10"))

# ───────── header detection ──────────
def _header_idx(path: Path) -> int:
    with path.open(encoding="utf-8", errors="ignore") as fp:
        for i, line in enumerate(fp):
            if line.count(",") >= 2:          # ≥ 3 columns looks like header
                return i
    return 0

# ───────── date helpers ──────────────
_NUM = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
def _extract_date(text: str) -> Optional[str]:
    m = _NUM.search(text)
    if m:
        try: return dp.parse(m.group(0)).strftime("%m/%d/%Y")
        except Exception: pass
    try: return dp.parse(text, fuzzy=True).strftime("%m/%d/%Y")
    except Exception: return None

def _exact_slice(tok: str, df: pd.DataFrame) -> pd.DataFrame | None:
    """
    1. Try strict date-object match.
    2. If empty, fall back to string-contains match (robust to hidden chars).
    """
    # 1) strict
    try: dt = pd.to_datetime(tok).date()
    except Exception: dt = None

    if "_cache" not in df.attrs:
        df.attrs["_cache"] = pd.to_datetime(
            df.iloc[:, 0].str.strip(), errors="coerce"
        ).dt.date

    if dt:
        hit = df[df.attrs["_cache"] == dt]
        if not hit.empty:
            return hit

    # 2) loose string contains
    mask = df.iloc[:, 0].str.contains(tok.lstrip("0"), regex=False, na=False)
    hit  = df[mask]
    return hit if not hit.empty else None

# ───────── adapter core ──────────────
def format_csv_for_prompt(question: str, query: Dict[str, Any]) -> str:
    root = Path(__file__).resolve().parents[2]
    csv  = root / query["file_path"]

    hdr = _header_idx(csv)
    df  = pd.read_csv(csv, dtype=str, engine="python",
                      skiprows=hdr, header=0)

    preview: pd.DataFrame | None = None

    # 1) direct date shortcut
    tok = _extract_date(question)
    if tok:
        preview = _exact_slice(tok, df)
        if preview is not None and not preview.empty:
            preview = preview.iloc[:MAX_ROWS]

    # 2) FAISS fallback
    if preview is None or preview.empty:
        rows = search_rows(question, str(csv), k=MAX_ROWS)
        preview = df.iloc[rows] if rows else df.iloc[:MAX_ROWS]

    # 3) column cap
    if preview.shape[1] > MAX_COLS:
        preview = preview.iloc[:, :MAX_COLS]

    header = (f"**CSV Preview (Date token={tok or '–'}):** "
              f"{len(df):,} total rows; "
              f"showing {len(preview)} row(s) × {preview.shape[1]} col(s)")
    return f"{header}\n\n```csv\n{preview.to_markdown(index=False)}\n```"
