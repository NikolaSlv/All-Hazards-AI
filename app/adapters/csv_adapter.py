"""
app/adapters/csv_adapter.py
────────────────────────────────────────────────────────────────────────────
Utility that turns a small slice of a CSV file into a Markdown snippet
suitable for an LLM prompt.

• Row / column limits are **configurable via environment variables**  
  ── MAX_CSV_RETR_ROWS  (default 10)  
  ── MAX_CSV_RETR_COLS  (default 10)

Example query object:
    {"source_type": "csv", "file_path": "data/foo.csv"}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pandas as pd

# ───────────────────────────── Config ──────────────────────────────
MAX_ROWS = int(os.getenv("MAX_CSV_RETR_ROWS", 10))
MAX_COLS = int(os.getenv("MAX_CSV_RETR_COLS", 10))


# ─────────────────── Formatter used by generation_service ──────────
def format_csv_for_prompt(query: Dict[str, Any]) -> str:
    """
    Build a Markdown snippet with
      • short summary (row-count, first N column names)
      • GitHub-flavoured Markdown preview table

    The preview table is capped at MAX_ROWS × MAX_COLS but will show the
    full data if the file is smaller than those limits.
    """
    # 1) Resolve full path relative to repo root
    repo_root = Path(__file__).resolve().parents[2]
    full_path = repo_root / query["file_path"]

    # 2) Count total data rows  (skip the header itself)
    with full_path.open(encoding="utf-8", errors="ignore") as fh:
        total_rows = max(sum(1 for _ in fh) - 1, 0)

    # 3) Read only the preview slice
    df_prev = pd.read_csv(
        full_path,
        nrows=MAX_ROWS,
        low_memory=False,
        dtype=str,
        skiprows=1,          # skip a metadata header row if you have one
    )

    # 4) Trim to first MAX_COLS columns (if necessary)
    if df_prev.shape[1] > MAX_COLS:
        df_prev = df_prev.iloc[:, :MAX_COLS]

    # 5) Compose summary header
    col_names = list(df_prev.columns)
    header = (
        f"**CSV Summary:** {total_rows} rows in file; "
        f"showing first {len(df_prev)} row(s) × {len(col_names)} column(s) → "
        + ", ".join(col_names)
    )

    # 6) Render GitHub-style Markdown table
    table_md = df_prev.to_markdown(index=False)

    # 7) Wrap in ```csv code-fence for clarity
    return f"{header}\n\n```csv\n{table_md}\n```"
