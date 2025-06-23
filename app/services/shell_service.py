import asyncio
from pathlib import Path

async def run_shell(file_path: str) -> str:
    """
    Runs the given Python file via subprocess and returns its stdout.
    The file_path is relative to the project root.
    """
    proj_root = Path(__file__).resolve().parents[2]
    full_path = proj_root / file_path

    if not full_path.exists():
        raise FileNotFoundError(f"No such file: {full_path}")

    # spawn a Python subprocess
    proc = await asyncio.create_subprocess_exec(
        "python", str(full_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Execution failed:\n{err}")

    return stdout.decode("utf-8", errors="ignore")
