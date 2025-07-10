#!/usr/bin/env python
"""
CSV catalog generator / updater.

• Scans data/*.csv and builds metadata (columns, row-count, date range, …)
• Appends/merges results into data/catalog.json under key "files"
"""
from __future__ import annotations

import json, logging, os, re
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from tqdm import tqdm

logger = logging.getLogger("csv_catalog_service")

# ───────────────────────────── paths ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR     = PROJECT_ROOT / "data"
CATALOG_FILE = DATA_DIR / "catalog.json"

# ────────────────────────── helpers ─────────────────────────────────────────
def compress_columns(cols: list[str]) -> list[str]:
    groups, others = defaultdict(set), []
    for c in cols:
        m = re.match(r"^(.+?)[_:]?(\d+)$", c)
        if m:
            groups[m.group(1)].add(int(m.group(2)))
        else:
            others.append(c)
    result = others[:]
    for prefix, nums in groups.items():
        nums = sorted(nums)
        if len(nums) <= 2:
            result += [f"{prefix}:{n}" for n in nums]
        else:
            result.append(f"{prefix}:1-{nums[-1]}")
    return result


def _find_header_idx(path: Path) -> int:
    """Return the first line index (0-based) containing a comma."""
    with path.open(encoding="utf-8", errors="ignore") as fp:
        for i, line in enumerate(fp):
            if "," in line:
                return i
    return 0


# ────────────────────────── catalog core ────────────────────────────────────
def _scan_csv_files() -> List[Dict[str, Any]]:
    """Return a list of CSV-metadata dicts (one per file)."""
    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))
    date_re   = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")

    items: List[Dict[str, Any]] = []

    for fname in tqdm(csv_files, desc="Cataloging CSV files", unit="file"):
        full = DATA_DIR / fname
        rel  = f"data/{fname}"

        header_idx = _find_header_idx(full)

        # total rows
        try:
            total = sum(1 for _ in full.open(encoding="utf-8", errors="ignore"))
            row_count = max(total - header_idx - 1, 0)
        except Exception:
            row_count = None

        # sample col-0 values
        try:
            df_samp = pd.read_csv(
                full, usecols=[0], skiprows=header_idx,
                header=0, nrows=10, dtype=str, engine="python"
            )
            sample_vals = list(df_samp.iloc[:, 0].dropna().astype(str))
        except Exception:
            sample_vals = []

        all_dates = bool(sample_vals) and all(date_re.match(v) for v in sample_vals)
        date_range, sample_rows = None, None

        if all_dates:
            dmin = dmax = None
            try:
                for chunk in pd.read_csv(
                    full, usecols=[0], parse_dates=[0],
                    skiprows=header_idx, header=0,
                    chunksize=100_000, engine="python", low_memory=True
                ):
                    col = chunk.iloc[:, 0].dropna()
                    if col.empty: continue
                    m, M = col.min(), col.max()
                    dmin = m if dmin is None else min(dmin, m)
                    dmax = M if dmax is None else max(dmax, M)
                if dmin is not None and dmax is not None:
                    date_range = f"{dmin.date()} to {dmax.date()}"
            except Exception:
                date_range = None
            if date_range is None:
                sample_rows = sample_vals
        else:
            sample_rows = sample_vals

        # columns
        try:
            df0  = pd.read_csv(full, nrows=0, skiprows=header_idx,
                               header=0, engine="python")
            cols = compress_columns(list(df0.columns))
        except Exception:
            cols = []

        items.append({
            "path":        rel,
            "columns":     cols,
            "row_count":   row_count,
            "date_range":  date_range,
            "sample_rows": sample_rows,
        })

    return items


def _load_existing() -> Dict[str, Any]:
    if not CATALOG_FILE.is_file():
        logger.info("Catalog file not found — creating new one at %s", CATALOG_FILE)
        return {"files": [], "pdfs": []}            # pdfs key for later merge
    with CATALOG_FILE.open(encoding="utf-8") as fp:
        return json.load(fp)


def _dedupe_merge(old: List[Dict[str, Any]],
                  new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {e["path"] for e in old}
    merged = old[:]
    for entry in new:
        if entry["path"] not in seen:
            merged.append(entry)
            seen.add(entry["path"])
    return merged


# ────────────────────────── public API ──────────────────────────────────────
def save_csv_catalog(path: Path = CATALOG_FILE) -> None:
    new_files = _scan_csv_files()
    base      = _load_existing()
    base.setdefault("files", [])
    base["files"] = _dedupe_merge(base["files"], new_files)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    logger.info("Updated catalog with %d CSV file(s) → %s",
                len(base["files"]), path)


def load_csv_catalog(path: Path = CATALOG_FILE) -> Dict[str, Any]:
    if not path.is_file():
        return {"files": []}
    return json.loads(path.read_text(encoding="utf-8"))


def render_csv_catalog_summary(cat: Dict[str, Any]) -> str:
    lines = ["Available CSV files:"]
    for f in cat.get("files", []):
        # rows
        rc = f.get("row_count")
        rc_text = "rows: ?" if rc is None else (
            f"rows: {rc}" if rc <= 10 else f"rows: {rc} (showing first 10)"
        )
        # dates / samples
        if f.get("date_range"):
            extra = f"; dates {f['date_range']}"
        elif f.get("sample_rows"):
            extra = f"; sample values: {', '.join(f['sample_rows'])}"
        else:
            extra = ""
        cols = ", ".join(f.get("columns", []))
        lines.append(f"- {f['path']}: {rc_text}{extra}; columns: {cols}")
    return "\n".join(lines)


# ─── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    save_csv_catalog()
