import os
import re
import json
import logging
from pathlib import Path
from collections import defaultdict

import pandas as pd
from tqdm import tqdm

# ── locate your project root & data dir ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
CATALOG_FILE = DATA_DIR / "catalog.json"

# ── module‐level logger ────────────────────────────────────────────────────
logger = logging.getLogger("catalog_service")

# ── helper to collapse runs of foo1, foo2, …, fooN → foo:1-N ────────────────
def compress_columns(cols: list[str]) -> list[str]:
    groups: dict[str, set[int]] = defaultdict(set)
    others: list[str]          = []

    for c in cols:
        m = re.match(r"^(.+?)[_:]?(\d+)$", c)
        if m:
            prefix, num = m.group(1), int(m.group(2))
            groups[prefix].add(num)
        else:
            others.append(c)

    result: list[str] = []
    result.extend(others)

    for prefix, nums in groups.items():
        sorted_nums = sorted(nums)
        if len(sorted_nums) <= 2:
            for n in sorted_nums:
                result.append(f"{prefix}:{n}")
        else:
            result.append(f"{prefix}:1-{sorted_nums[-1]}")

    return result

# ── build the catalog dict ─────────────────────────────────────────────────
def generate_catalog() -> dict:
    logger.info("Starting catalog generation from %s", DATA_DIR)
    if not DATA_DIR.is_dir():
        logger.error("Data directory not found: %s", DATA_DIR)
        raise FileNotFoundError(f"data/ folder not found at {DATA_DIR!s}")

    catalog: dict = {"files": []}
    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))

    for fname in tqdm(csv_files, desc="Cataloging files", unit="file"):
        full_path = DATA_DIR / fname
        rel_path  = f"data/{fname}"

        try:
            # read header row (skip one row if you have metadata)
            df   = pd.read_csv(full_path, nrows=0, skiprows=1)
            cols = compress_columns(list(df.columns))
        except Exception as e:
            logger.warning("Failed to read columns from %s: %s", fname, e)
            cols = []

        catalog["files"].append({
            "path":    rel_path,
            "columns": cols,
        })

    logger.info("Catalog built: %d file(s) found", len(catalog["files"]))
    return catalog

# ── save & load helpers ────────────────────────────────────────────────────
def save_catalog(path: Path = CATALOG_FILE) -> None:
    cat = generate_catalog()
    path.write_text(json.dumps(cat, indent=2), encoding="utf-8")
    logger.info("Wrote catalog to %s", path)

def load_catalog(path: Path = CATALOG_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

# ── optional human-friendly summary ────────────────────────────────────────
def render_catalog_summary(cat: dict) -> str:
    lines = ["Available files:"]
    for f in cat.get("files", []):
        cols = f.get("columns", [])
        lines.append(f"- {f['path']}: {', '.join(cols)}")
    return "\n".join(lines)

# ── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    # configure a simple console logger if run as a script
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO
    )
    save_catalog()
