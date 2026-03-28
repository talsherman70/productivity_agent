from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router
import os

app = FastAPI(
    title="Productivity Agent",
    description="A multi-agent productivity assistant",
    version="0.1.0"
)

# Serve everything in app/static/ as static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(router)


@app.get("/")
def root():
    """Opens the chat UI."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Productivity Agent is running"}