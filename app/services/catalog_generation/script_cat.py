import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from tqdm import tqdm

# ──────────────────────── Directories & Files ─────────────────────────────
# climb out of `app/` into project root, then into root-level user_data/
USER_DATA_DIR = Path(__file__).resolve().parents[3] / "user_data"
CATALOG_FILE  = USER_DATA_DIR / "script_catalog.json"

# ──────────────────────── Module‐level Logger ─────────────────────────────
logger = logging.getLogger("script_catalog_service")


def generate_script_catalog() -> Dict[str, Any]:
    """
    Scan `user_data/` (in the project root) for .py files.
    Returns:
      {
        "scripts": [
          { "name": "foo.py", "path": "user_data/foo.py" },
          …
        ]
      }
    """
    logger.info("Scanning for Python scripts in %s", USER_DATA_DIR)
    catalog: Dict[str, Any] = {"scripts": []}

    if not USER_DATA_DIR.is_dir():
        logger.warning("No user_data directory found at %s", USER_DATA_DIR)
        return catalog

    all_py = sorted(f for f in os.listdir(USER_DATA_DIR) if f.lower().endswith(".py"))

    # wrap with tqdm
    for fname in tqdm(all_py, desc="Cataloging Python scripts", unit="script"):
        catalog["scripts"].append({
            "name": fname,
            "path": f"user_data/{fname}",
        })

    logger.info("Found %d script(s)", len(catalog["scripts"]))
    return catalog


def render_script_catalog_summary(cat: Dict[str, Any]) -> str:
    """
    Produce a human-readable summary, e.g.:

    Available Python scripts:
    - foo.py: user_data/foo.py
    - bar.py: user_data/bar.py
    """
    lines = ["Available Python scripts:"]
    for s in cat.get("scripts", []):
        lines.append(f"- {s['name']}: {s['path']}")
    return "\n".join(lines)


def save_script_catalog(path: Path = CATALOG_FILE) -> None:
    """
    Generate the catalog and write it out as JSON to the root user_data/script_catalog.json.
    """
    cat = generate_script_catalog()

    # ensure the user_data directory exists
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps(cat, indent=2), encoding="utf-8")
    logger.info("Wrote script catalog to %s", path)


def load_script_catalog(path: Path = CATALOG_FILE) -> Dict[str, Any]:
    """
    Load the existing catalog JSON from root user_data/script_catalog.json.
    """
    if not path.is_file():
        logger.error("Script catalog file not found: %s", path)
        return {"scripts": []}
    return json.loads(path.read_text(encoding="utf-8"))


# ── CLI entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    # simple console logger when running as script
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    save_script_catalog()
