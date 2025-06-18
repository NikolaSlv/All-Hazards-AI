from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

from app.api import ui, planner
from app.services.catalog_generation.csv_cat import save_csv_catalog

# ────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run once, before the first request, to build the CSV catalog
    save_csv_catalog()
    yield
    # (could add shutdown logic here if needed)

app = FastAPI(
    title="RAG Prototype",
    lifespan=lifespan,
)

# mount our JS/CSS under /static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# include routers
app.include_router(ui.router)
app.include_router(planner.router)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
