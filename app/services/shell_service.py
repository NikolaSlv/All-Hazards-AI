"""
Run an uploaded Python script in this project’s virtual-environment
and return its stdout.

The blocking `subprocess.run()` is off-loaded to a background thread
(`asyncio.to_thread`) so the coroutine works on any event-loop
—including the Selector loop that Uvicorn uses on Windows.

If the target script exits with a non-zero status, the raised
RuntimeError will contain its *stderr*.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Final


def _find_venv_python(start: Path) -> Path:
    """
    Walk up from *start* until we find a ".venv" directory and
    return the path to its Python executable.

    Raises FileNotFoundError if ".venv" is not found.
    """
    for parent in [start, *start.parents]:
        venv_dir = parent / ".venv"
        if venv_dir.is_dir():
            # Windows: Scripts\python.exe   • POSIX: bin/python
            sub = "Scripts" if os.name == "nt" else "bin"
            python_path = venv_dir / sub / ("python.exe" if os.name == "nt" else "python")
            if python_path.exists():
                return python_path
            # Edge-case: symlinked envs or custom names → fall back to sys.executable
            break
    raise FileNotFoundError("Could not locate a '.venv' directory "
                            "above the current file.")


# ── Locate the venv interpreter once at import-time ─────────────────────────
_THIS_FILE: Final = Path(__file__).resolve()
PYTHON_VENV: Final = _find_venv_python(_THIS_FILE.parent)


async def run_shell(file_path: str) -> str:
    """
    Execute the uploaded script *inside the project's venv* and
    return **stdout only** as a string.

    Example
    -------
    >>> out = await run_shell('/tmp/uploaded/myscript.py')
    >>> print(out)
    """
    full_path = Path(file_path).resolve()
    if not full_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    def _blocking_exec() -> str:
        proc = subprocess.run(
            [str(PYTHON_VENV), str(full_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "Script exited with non-zero status")
        return proc.stdout

    # Off-load the blocking subprocess to a thread
    return await asyncio.to_thread(_blocking_exec)


# ── Quick manual test (run this file directly) ─────────────────────────────−
if __name__ == "__main__":
    async def _demo() -> None:
        # Replace with an actual test script path
        test_py = Path.cwd() / "hello.py"
        print(await run_shell(str(test_py)))

    asyncio.run(_demo())
