#!/usr/bin/env python
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
import tempfile
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
            python_exec = "python.exe" if os.name == "nt" else "python"
            python_path = venv_dir / sub / python_exec
            if python_path.exists():
                return python_path
            break
    raise FileNotFoundError("Could not locate a '.venv' directory above the current file.")


_THIS_FILE: Final = Path(__file__).resolve()
PYTHON_VENV: Final = _find_venv_python(_THIS_FILE.parent)


async def run_shell(file_path: str) -> str:
    """
    Execute the uploaded script *inside the project's venv* and return **stdout**.
    If stdout exceeds MAX_OUTPUT_CHARS, spill to disk, index, and return a marker.
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

    output = await asyncio.to_thread(_blocking_exec)

    # If output is too large, spill to disk & index
    max_chars = int(os.getenv("MAX_OUTPUT_CHARS", "200000"))
    if len(output) > max_chars:
        out_dir = Path(__file__).parents[2] / "user_data" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", dir=out_dir)
        tmp_file.write(output)
        tmp_file.close()
        tmp_path = tmp_file.name

        # index this spill just like PDFs
        from app.services.vector_index import build_script_output_index
        build_script_output_index(tmp_path)

        # return marker instead of the full dump
        return f"__INDEXED_OUTPUT__:{tmp_path}"

    return output


if __name__ == "__main__":
    import asyncio as _asyncio

    async def _demo() -> None:
        test_py = Path.cwd() / "hello.py"
        print(await run_shell(str(test_py)))

    _asyncio.run(_demo())
