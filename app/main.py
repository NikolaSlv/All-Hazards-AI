from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import ui, planner

app = FastAPI(title="RAG Prototype")

# mount our JS/CSS under /static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# include routers
app.include_router(ui.router)
app.include_router(planner.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
