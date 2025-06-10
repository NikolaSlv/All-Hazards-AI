from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.schemas.question import Question
from app.services.planner_service import plan

# Planner API Router
router = APIRouter(prefix="/planner", tags=["planner"])

@router.post("/", response_class=JSONResponse)
async def planner_endpoint(q: Question):
    """
    Receives a question and returns the planner's output.
    """
    try:
        result = await plan(q.question)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
