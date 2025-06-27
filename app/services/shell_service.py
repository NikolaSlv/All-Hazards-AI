"""
Run an uploaded Python script and return its stdout.

Implemented with `asyncio.to_thread()` so it works on every event-loop,
including the Selector loop that Uvicorn uses on Windows.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


async def run_shell(file_path: str) -> str:
    """
    Execute `python <file_path>` and return **only stdout**.
    If the script exits with a non-zero status, raise RuntimeError(stderr).
    Works on Windows & POSIX because we off-load the blocking call
    to a background thread.
    """
    full_path = Path(file_path)
    if not full_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    def _blocking_exec() -> str:
        # Use the same interpreter that is running the server
        proc = subprocess.run(
            ["python", str(full_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return proc.stdout

    # run the blocking call in the default ThreadPoolExecutor
    return await asyncio.to_thread(_blocking_exec)
