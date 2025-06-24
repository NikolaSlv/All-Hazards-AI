from typing import Dict, Any

from app.services.shell_service import run_shell

async def format_shell_for_prompt(query: Dict[str, Any]) -> str:
    """
    Given {"source_type":"shell", "file_path":"app/user_data/foo.py"},
    runs that script via run_shell() and returns a Markdown block:

    **Shell Execution of `app/user_data/foo.py`**

    ```
    <stdout of foo.py>
    ```
    """
    path = query["file_path"]
    output = await run_shell(path)
    return (
        f"**Shell Execution of `{path}`**\n\n"
        f"```\n{output.strip()}\n```"
    )
