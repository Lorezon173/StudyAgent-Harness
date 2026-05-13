import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.database import init_db
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.chat_stream import router as chat_stream_router
from app.api.chat_multi import router as chat_multi_router
from app.api.eval import router as eval_router
from app.api.knowledge import router as knowledge_router
from app.api.sessions import router as sessions_router
from app.api.profile import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="StudyAgent", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(chat_stream_router, prefix="/api")
app.include_router(chat_multi_router, prefix="/api")
app.include_router(eval_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(profile_router, prefix="/api")


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
