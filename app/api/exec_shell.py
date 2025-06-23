from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pathlib import Path
import shutil

from app.services.shell_service import run_shell

router = APIRouter(prefix="/exec_shell", tags=["exec_shell"])

@router.post("", response_class=PlainTextResponse)
async def exec_shell_endpoint(file: UploadFile = File(...)):
    """
    1) Accept a .py file upload via multipart/form-data
    2) Save it under PROJECT_ROOT/user_data/
    3) Execute it with run_shell() and return stdout
    """
    # project root = two levels up from this file
    project_root   = Path(__file__).resolve().parents[2]
    user_data_dir  = project_root / "user_data"
    user_data_dir.mkdir(exist_ok=True)

    # save the uploaded file
    target = user_data_dir / file.filename
    with open(target, "wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    # execute it
    rel_path = f"user_data/{file.filename}"
    try:
        output = await run_shell(rel_path)
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
