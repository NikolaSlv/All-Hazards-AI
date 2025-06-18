from pathlib import Path
from typing import Any, Dict

import pandas as pd

def format_csv_for_prompt(query: Dict[str, Any]) -> str:
    """
    Given:
      query = {"source_type":"csv", "file_path":"data/foo.csv"}

    Returns a string suitable for an LLM prompt that includes:
    - A summary: total rows; first up to 10 column names
    - A Markdown preview of up to the first 10 rows by 10 columns
    """

    # 1) Resolve the full file path
    repo_root = Path(__file__).resolve().parents[2]
    full_path = repo_root / query["file_path"]

    # 2) Count total rows by streaming (skip header line)
    with open(full_path, encoding="utf-8", errors="ignore") as f:
        total_lines = sum(1 for _ in f) - 1
        total_rows  = max(total_lines, 0)

    # 3) Read only the first 10 rows (infer dtypes, low_memory=False to silence warnings)
    df_preview = pd.read_csv(
        full_path,
        nrows=10,
        low_memory=False,
        dtype=str,
        skiprows=1,  # Skip header metadata row
    )

    # 4) Limit to the first 10 columns
    if df_preview.shape[1] > 10:
        df_preview = df_preview.iloc[:, :10]

    # 5) Build the summary header
    preview_cols = list(df_preview.columns)
    header = (
        f"**CSV Summary:** {total_rows} rows; "
        f"columns (showing first {len(preview_cols)}): {', '.join(preview_cols)}"
    )

    # 6) Render the preview as a GitHub-flavored Markdown table
    table_md = df_preview.to_markdown(index=False)

    # 7) Wrap it in a CSV code fence for clarity
    snippet_text = (
        f"{header}\n\n"
        f"```csv\n"
        f"{table_md}\n"
        f"```"
    )

    return snippet_text
