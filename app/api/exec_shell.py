from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pathlib import Path
import shutil

from app.services.shell_service import run_shell
from app.services.catalog_generation.script_cat import save_script_catalog

router = APIRouter(prefix="/exec_shell", tags=["exec_shell"])

@router.post("", response_class=PlainTextResponse)
async def exec_shell_endpoint(file: UploadFile = File(...)):
    """
    1) Accept a .py upload via multipart/form-data
    2) Save under project_root/user_data/
    3) Rebuild the script catalog immediately
    4) Execute it and return stdout
    """
    # 1) Ensure user_data dir exists at project root
    project_root  = Path(__file__).resolve().parents[2]  # api → app → project
    user_data_dir = project_root / "user_data"
    user_data_dir.mkdir(exist_ok=True)

    # 2) Save the uploaded script
    target = user_data_dir / file.filename
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    # 3) Immediately regenerate the script catalog
    save_script_catalog()  

    # 4) Run the script and return its stdout
    rel_path = f"user_data/{file.filename}"
    try:
        output = await run_shell(rel_path)
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
