from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="Productivity Agent",
    description="A multi-agent productivity assistant",
    version="0.1.0"
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Productivity Agent is running"}