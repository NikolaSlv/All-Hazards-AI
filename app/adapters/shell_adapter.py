from typing import Dict, Any

from app.services.shell_service import run_shell

async def format_shell_for_prompt(query: Dict[str, Any]) -> str:
    """
    Given {"source_type":"shell", "file_path":"user_data/foo.py"},
    runs that script via run_shell() and returns either:

    - If the script output exceeded MAX_OUTPUT_CHARS, run_shell() will
      have written it to disk and returned "__INDEXED_OUTPUT__:/full/path".
      In that case we return the marker verbatim so the prompt builder
      can do a RAG lookup.

    - Otherwise we return the actual stdout as a Markdown code block:

    **Shell Execution of `user_data/foo.py`**

    ```
    <stdout of foo.py>
    ```
    """
    path = query["file_path"]
    output = await run_shell(path)

    # If we've spilled & indexed the output, just return the marker
    if output.startswith("__INDEXED_OUTPUT__:"):
        return output.strip()

    # Otherwise inline the real stdout
    return (
        f"**Shell Execution of `{path}`**\n\n"
        f"```\n{output.strip()}\n```"
    )
