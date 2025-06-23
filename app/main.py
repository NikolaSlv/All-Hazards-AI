from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import ui, stream, exec_shell

app = FastAPI(title="RAG Prototype")

# serve static assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# include routers
app.include_router(ui.router)
app.include_router(stream.router)
app.include_router(exec_shell.router)
