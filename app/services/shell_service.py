import asyncio
from pathlib import Path

async def run_shell(file_path: str) -> str:
    """
    Asynchronously execute `python <file_path>` and return its stdout.
    Raises if the script exits non-zero.
    """
    full = Path(file_path)
    if not full.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    proc = await asyncio.create_subprocess_exec(
        "python", str(full),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore"))
    return out.decode(errors="ignore")
