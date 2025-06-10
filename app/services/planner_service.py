import asyncio
from typing import Any, Dict

async def plan(question: str) -> Dict[str, Any]:
    """
    Stub for your Planner LLM integration.
    For now, it just echoes back the question in a dict.
    Replace this with the real LLM call when ready.
    """
    # Simulate async work / latency
    await asyncio.sleep(0.1)
    return {"question_received": question}
