from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.planner_service import plan
from app.services.generation_service import generate_answer_stream

router = APIRouter()

@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            q   = (msg.get("question") or "").strip()
            if not q:
                await ws.send_text("[server] empty question")
                continue

            plan_obj = await plan(q)

            async for chunk in generate_answer_stream(q, plan_obj["source_queries"]):
                await ws.send_text(chunk)

            await ws.send_text("[DONE]")
    except WebSocketDisconnect:
        pass
