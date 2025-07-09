#!/usr/bin/env python
"""
Turn a *relevant* slice of a CSV into a Markdown snippet for the LLM.

• Direct-match: if the user’s question contains an explicit date like
  “03/16/2023”, we grab that row in O(1) and skip FAISS.
• Otherwise: semantic retrieval via search_rows() as before.

Env vars
--------
MAX_CSV_RETR_ROWS, MAX_CSV_RETR_COLS  (same as before)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from app.services.vector_index import search_rows

# ───────────────────────────────────────── config ──────────────────────────────────────
MAX_ROWS = int(os.getenv("MAX_CSV_RETR_ROWS", "10"))
MAX_COLS = int(os.getenv("MAX_CSV_RETR_COLS", "10"))

# regex: 1- or 2-digit month/day, 2- or 4-digit year
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")

# ───────────────────────────────────── helpers ─────────────────────────────────────────
def _extract_date_token(text: str) -> Optional[str]:
    """Return the first raw date token in *text* or None."""
    m = _DATE_RE.search(text)
    return m.group(0) if m else None


def _direct_date_slice(date_token: str, df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Fast path: filter rows whose *Date* column equals the user's date.
    Works on all OSes because we compare datetime.date objects instead
    of using strftime flags like %-m or %#m.
    """
    try:
        dt_obj = pd.to_datetime(date_token, errors="raise")
    except (ValueError, TypeError):
        return None

    # Cache the parsed column so we don’t re-parse on every call
    if "_dt_cache" not in df.attrs:
        df.attrs["_dt_cache"] = pd.to_datetime(df.iloc[:, 0], errors="coerce").dt.date

    mask = df.attrs["_dt_cache"] == dt_obj.date()
    hit  = df[mask]
    return hit if not hit.empty else None

# ─────────────────────────────────── adapter API ───────────────────────────────────────
def format_csv_for_prompt(question: str, query: Dict[str, Any]) -> str:
    """
    Parameters
    ----------
    question : str
    query    : {"source_type":"csv", "file_path":"data/foo.csv"}
    """
    repo_root = Path(__file__).resolve().parents[2]
    full_path = repo_root / query["file_path"]

    # Read once, all downstream ops use the same df
    df = pd.read_csv(full_path, dtype=str, engine="python", skiprows=1)

    # 1) Try the direct-date shortcut
    token = _extract_date_token(question)
    if token:
        df_prev = _direct_date_slice(token, df)
        if df_prev is not None and not df_prev.empty:
            df_prev = df_prev.iloc[:MAX_ROWS]      # still respect row cap
    # 2) Otherwise fall back to FAISS
    if token is None or df_prev is None or df_prev.empty:
        row_ids: List[int] = search_rows(question, str(full_path), k=MAX_ROWS)
        if not row_ids:                           # last-chance fallback
            row_ids = list(range(min(MAX_ROWS, len(df))))
        df_prev = df.iloc[row_ids]

    # Column cap
    if df_prev.shape[1] > MAX_COLS:
        df_prev = df_prev.iloc[:, :MAX_COLS]

    header = (
        f"**CSV Preview:** {len(df):,} total rows; "
        f"showing {len(df_prev)} row(s) × {df_prev.shape[1]} col(s)"
    )
    return f"{header}\n\n```csv\n{df_prev.to_markdown(index=False)}\n```"
