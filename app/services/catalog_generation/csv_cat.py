import os
import re
import json
import logging
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime

import pandas as pd
from tqdm import tqdm

logger = logging.getLogger("csv_catalog_service")

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR     = PROJECT_ROOT / "data"
CATALOG_FILE = DATA_DIR / "catalog.json"

# ─── Column compressor ────────────────────────────────────────────────────────
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

# ─── Find header row index ───────────────────────────────────────────────────
def _find_header_idx(path: Path) -> int:
    """Return the first line index (0-based) containing a comma."""
    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
        for i, line in enumerate(fp):
            if "," in line:
                return i
    return 0

# ─── Build the catalog entries ───────────────────────────────────────────────
def generate_csv_catalog() -> dict:
    logger.info("Starting CSV catalog generation from %s", DATA_DIR)
    if not DATA_DIR.is_dir():
        logger.error("Data directory not found: %s", DATA_DIR)
        raise FileNotFoundError(DATA_DIR)

    catalog = {"files": []}
    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))
    date_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")

    for fname in tqdm(csv_files, desc="Cataloging CSV files", unit="file"):
        full = DATA_DIR / fname
        rel  = f"data/{fname}"

        # 1) Detect header row
        header_idx = _find_header_idx(full)

        # 2) Count total rows after header
        try:
            total_lines = sum(1 for _ in open(full, "r", encoding="utf-8", errors="ignore"))
            row_count   = max(total_lines - header_idx - 1, 0)
        except Exception:
            row_count = None

        # 3) Sample first 10 data‐values of column 0
        try:
            df_sample = pd.read_csv(
                full,
                usecols=[0],
                skiprows=header_idx,
                header=0,
                nrows=10,
                dtype=str,
                engine="python",
            )
            sample_vals = list(df_sample.iloc[:, 0].dropna().astype(str))
        except Exception:
            sample_vals = []

        all_dates = bool(sample_vals) and all(date_pattern.match(v) for v in sample_vals)

        date_range  = None
        sample_rows = None

        if all_dates:
            # 4) Stream‐parse entire column for true min/max dates
            dmin = None
            dmax = None
            try:
                for chunk in pd.read_csv(
                    full,
                    usecols=[0],
                    parse_dates=[0],
                    skiprows=header_idx,
                    header=0,
                    chunksize=100_000,
                    engine="python",
                    low_memory=True,
                ):
                    col = chunk.iloc[:, 0].dropna()
                    if col.empty:
                        continue
                    m, M = col.min(), col.max()
                    dmin = m if dmin is None else min(dmin, m)
                    dmax = M if dmax is None else max(dmax, M)
                if dmin is not None and dmax is not None:
                    date_range = f"{dmin.date().isoformat()} to {dmax.date().isoformat()}"
            except Exception:
                date_range = None

            if date_range is None:
                sample_rows = sample_vals
        else:
            sample_rows = sample_vals

        # 5) Read real header for columns
        try:
            df0  = pd.read_csv(full, nrows=0, skiprows=header_idx, header=0, engine="python")
            cols = compress_columns(list(df0.columns))
        except Exception:
            cols = []

        catalog["files"].append({
            "path":        rel,
            "columns":     cols,
            "row_count":   row_count,
            "date_range":  date_range,
            "sample_rows": sample_rows,
        })

    logger.info("CSV catalog built: %d file(s)", len(catalog["files"]))
    return catalog

# ─── Save & load ────────────────────────────────────────────────────────────
def save_csv_catalog(path: Path = CATALOG_FILE) -> None:
    cat = generate_csv_catalog()
    path.write_text(json.dumps(cat, indent=2), encoding="utf-8")
    logger.info("Wrote CSV catalog to %s", path)

def load_csv_catalog(path: Path = CATALOG_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

# ─── Human‐friendly summary ──────────────────────────────────────────────────
def render_csv_catalog_summary(cat: dict) -> str:
    lines = ["Available CSV files:"]
    for f in cat.get("files", []):
        # row count
        rc = f.get("row_count")
        if rc is None:
            rc_text = "rows: ?"
        elif rc > 10:
            rc_text = f"rows: {rc} (showing first 10)"
        else:
            rc_text = f"rows: {rc}"

        # date range or sample values
        if f.get("date_range"):
            extra = f"; dates {f['date_range']}"
        elif f.get("sample_rows"):
            samp = ", ".join(f["sample_rows"])
            extra = f"; sample values: {samp}"
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
