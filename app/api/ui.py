from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    """
    Renders the main HTML template with the form.
    """
    return templates.TemplateResponse(
        "index.html", 
        {"request": request}
    )
