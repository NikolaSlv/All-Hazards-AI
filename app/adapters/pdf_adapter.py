#!/usr/bin/env python
"""
PDF → prompt snippet.

query = {"source_type":"pdf", "file_path":"data/foo.pdf"}
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pypdf import PdfReader
from app.services.vector_index import search_pdf_chunks

MAX_ROWS = int(os.getenv("MAX_CSV_RETR_ROWS", "10"))  # reuse same caps
CHAR_CAP = 2000                                       # chars per FAISS excerpt
PAGE_RE  = re.compile(r"page\s+(\d+)", re.IGNORECASE)

def format_pdf_for_prompt(question: str, query: Dict[str, Any]) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    pdf_path  = repo_root / query["file_path"]
    reader    = PdfReader(str(pdf_path))
    total     = len(reader.pages)

    # 1) If the user explicitly mentions a page number, show that page in full
    m = PAGE_RE.search(question)
    if m:
        pg = int(m.group(1))
        if 1 <= pg <= total:
            raw = reader.pages[pg - 1].extract_text() or ""
            text = raw.strip()
            return (
                f"**PDF Preview (full page {pg}):** {pdf_path.name}\n\n"
                "```text\n"
                f"— Page {pg} of {total} —\n"
                f"{text}\n"
                "```"
            )

    # 2) Otherwise fall back to FAISS‐based retrieval of up to MAX_ROWS chunks
    locs: List[Tuple[int,int]] = search_pdf_chunks(question, pdf_path, k=MAX_ROWS)
    if not locs:
        # if FAISS finds nothing, show first page as a last resort
        locs = [(1, 0)]

    excerpts: List[str] = []
    for pg, _ in locs:
        if not (1 <= pg <= total):
            continue
        raw = reader.pages[pg - 1].extract_text() or ""
        snippet = raw.replace("\n", " ").strip()[:CHAR_CAP]
        excerpts.append(f"— Page {pg} —\n{snippet}…")

    header = f"**PDF Preview:** {pdf_path.name} — {len(excerpts)} excerpt(s)"
    body   = "\n\n".join(excerpts)
    return f"{header}\n\n```text\n{body}\n```"
