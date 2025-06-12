import os
import re
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── 1) locate your project root & data dir ────────────────────────────────────
# this file lives at PROJECT_ROOT/app/services/catalog_service.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
CATALOG_FILE = DATA_DIR / "catalog.json"

# ── 2) helper to collapse runs of foo1, foo2, …, fooN → foo:1-N ────────────────
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
    # keep non-numeric suffix columns first
    result.extend(others)

    # now collapse each numeric group
    for prefix, nums in groups.items():
        sorted_nums = sorted(nums)
        if len(sorted_nums) <= 2:
            # if just one or two entries, list them explicitly
            for n in sorted_nums:
                result.append(f"{prefix}:{n}")
        else:
            # collapse into prefix:1-N using ASCII hyphen
            result.append(f"{prefix}:1-{sorted_nums[-1]}")

    return result

# ── 3) build the catalog dict ─────────────────────────────────────────────────
def generate_catalog() -> dict:
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"data/ folder not found at {DATA_DIR!s}")

    catalog: dict = {"files": []}

    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.lower().endswith((".csv", ".txt")):
            continue

        full_path = DATA_DIR / fname
        rel_path  = f"data/{fname}"

        # read only header row to get column names
        try:
            df    = pd.read_csv(full_path, nrows=0, skiprows=1)
            cols  = list(df.columns)
            cols  = compress_columns(cols)
        except Exception:
            cols = []

        catalog["files"].append({
            "path":    rel_path,
            "columns": cols,
        })

    return catalog

# ── 4) save & load helpers ───────────────────────────────────────────────────
def save_catalog(path: Path = CATALOG_FILE) -> None:
    cat = generate_catalog()
    path.write_text(json.dumps(cat, indent=2), encoding="utf-8")
    print(f"📝 Wrote catalog to {path!s}")

def load_catalog(path: Path = CATALOG_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

# ── 5) (optional) human-friendly summary ────────────────────────────────────
def render_catalog_summary(cat: dict) -> str:
    lines = ["Available files:"]
    for f in cat.get("files", []):
        cols = f.get("columns", [])
        lines.append(f"- {f['path']}: {', '.join(cols)}")
    return "\n".join(lines)

# ── 6) CLI entrypoint ───────────────────────────────────────────────────────
if __name__ == "__main__":
    save_catalog()
