#!/usr/bin/env python
"""
Python-script catalog generator / updater.

• Scans project-root `user_data/` for *.py files
• Merges results into user_data/script_catalog.json under key "scripts"
"""
from __future__ import annotations

import json, logging, os
from pathlib import Path
from typing import Dict, Any, List

from tqdm import tqdm

# ──────────────────────── Directories & Files ─────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parents[3]
USER_DATA_DIR = PROJECT_ROOT / "user_data"
CATALOG_FILE  = USER_DATA_DIR / "script_catalog.json"

logger = logging.getLogger("script_catalog_service")

# ─────────────────────────── helpers ───────────────────────────────────────
def _scan_scripts() -> List[Dict[str, str]]:
    """Return [{"name": "foo.py", "path": "user_data/foo.py"}, …]."""
    if not USER_DATA_DIR.is_dir():
        logger.warning("No user_data directory at %s", USER_DATA_DIR)
        return []

    all_py = sorted(f for f in os.listdir(USER_DATA_DIR) if f.lower().endswith(".py"))
    entries: List[Dict[str, str]] = []
    for fname in tqdm(all_py, desc="Cataloging Python scripts", unit="script"):
        entries.append({"name": fname, "path": f"user_data/{fname}"})
    return entries


def _load_existing() -> Dict[str, Any]:
    if not CATALOG_FILE.is_file():
        logger.info("Script catalog not found — creating new one at %s", CATALOG_FILE)
        return {"scripts": []}
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def _dedupe_merge(old: List[Dict[str, str]],
                  new: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = {e["path"] for e in old}
    merged = old[:]
    for entry in new:
        if entry["path"] not in seen:
            merged.append(entry)
            seen.add(entry["path"])
    return merged

# ────────────────────────── public API ─────────────────────────────────────
def save_script_catalog(path: Path = CATALOG_FILE) -> None:
    """
    Scan user_data/ for *.py files and merge into script_catalog.json.
    """
    new_scripts = _scan_scripts()
    base        = _load_existing()
    base["scripts"] = _dedupe_merge(base.get("scripts", []), new_scripts)

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    logger.info("Updated script catalog with %d script(s) → %s",
                len(base["scripts"]), path)


def load_script_catalog(path: Path = CATALOG_FILE) -> Dict[str, Any]:
    if not path.is_file():
        return {"scripts": []}
    return json.loads(path.read_text(encoding="utf-8"))


def render_script_catalog_summary(cat: Dict[str, Any]) -> str:
    lines = ["Available Python scripts:"]
    for s in cat.get("scripts", []):
        lines.append(f"- {s['name']}: {s['path']}")
    return "\n".join(lines)

# ── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    save_script_catalog()
