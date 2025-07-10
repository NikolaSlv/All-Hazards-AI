#!/usr/bin/env python
"""
PDF catalog generator.

• Scans the project-level `data/` folder for .pdf files
• Appends basic metadata (file name + rel-path) to the existing
  CSV catalog JSON (`data/catalog.json`)

Public API
----------
save_pdf_catalog()   → writes/updates catalog JSON
load_pdf_catalog()   → returns dict with {"pdfs": […]}
render_pdf_catalog_summary(cat) → human-readable summary
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any

from tqdm import tqdm

# ───────────────────────────── paths & logger ──────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR     = PROJECT_ROOT / "data"
CATALOG_FILE = DATA_DIR / "catalog.json"

logger = logging.getLogger("pdf_catalog_service")


# ───────────────────────────── helpers ─────────────────────────────────────
def _scan_pdfs() -> List[Dict[str, str]]:
    """Return [{"name": "foo.pdf", "path": "data/foo.pdf"}, …]."""
    pdfs = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".pdf"))
    entries: List[Dict[str, str]] = []
    for fname in tqdm(pdfs, desc="Cataloging PDFs", unit="pdf"):
        entries.append({"name": fname, "path": f"data/{fname}"})
    return entries


def _load_existing() -> Dict[str, Any]:
    if not CATALOG_FILE.is_file():
        logger.warning("Base catalog does not exist yet: %s", CATALOG_FILE)
        return {"files": [], "pdfs": []}  # CSV service will create "files"
    with CATALOG_FILE.open(encoding="utf-8") as fp:
        return json.load(fp)


def _dedupe_merge(old: List[Dict[str, str]], new: List[Dict[str, str]]
                  ) -> List[Dict[str, str]]:
    """Merge without duplicating identical {'name','path'} entries."""
    seen = {(e["name"], e["path"]) for e in old}
    merged = old[:]
    for e in new:
        tup = (e["name"], e["path"])
        if tup not in seen:
            merged.append(e)
            seen.add(tup)
    return merged


# ───────────────────────────── public API ──────────────────────────────────
def save_pdf_catalog(path: Path = CATALOG_FILE) -> None:
    """
    Append/merge PDF metadata into data/catalog.json.
    Run this *after* save_csv_catalog().
    """
    base = _load_existing()
    base.setdefault("pdfs", [])
    base["pdfs"] = _dedupe_merge(base["pdfs"], _scan_pdfs())

    # ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    logger.info("Updated catalog with %d PDF(s) → %s", len(base["pdfs"]), path)


def load_pdf_catalog(path: Path = CATALOG_FILE) -> Dict[str, Any]:
    """
    Return {"pdfs": […]}. Falls back to empty list if catalog missing.
    """
    if not path.is_file():
        logger.warning("Catalog JSON not found: %s", path)
        return {"pdfs": []}
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj.setdefault("pdfs", [])
    return obj


def render_pdf_catalog_summary(cat: Dict[str, Any]) -> str:
    """
    Produce a human-readable summary like:

    Available PDF files:
    - FEMA_2023_report.pdf: data/FEMA_2023_report.pdf
    - NOAA_hurricanes.pdf:  data/NOAA_hurricanes.pdf
    """
    lines = ["Available PDF files:"]
    for p in cat.get("pdfs", []):
        lines.append(f"- {p['name']}: {p['path']}")
    return "\n".join(lines)


# ── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    save_pdf_catalog()
