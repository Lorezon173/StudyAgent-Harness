import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="LearningAgent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


if os.path.exists("web/dist"):
    app.mount("/assets", StaticFiles(directory="web/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_vue(full_path: str):
        file_path = f"web/dist/{full_path}"
        if os.path.exists(file_path) and not full_path.startswith("api"):
            return FileResponse(file_path)
        return FileResponse("web/dist/index.html")
