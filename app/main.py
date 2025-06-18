from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

from app.api import ui, stream
from app.services.catalog_generation.csv_cat import save_csv_catalog

@asynccontextmanager
async def lifespan(app: FastAPI):
    save_csv_catalog()
    yield

app = FastAPI(title="RAG Prototype", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ui.router)
app.include_router(stream.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
