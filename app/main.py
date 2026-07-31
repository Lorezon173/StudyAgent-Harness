import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
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
    DIST = (Path(__file__).resolve().parent.parent / "web" / "dist").resolve()

    @app.get("/{full_path:path}")
    async def serve_vue(full_path: str):
        # ① API 命名空间不进 SPA fallback：缺失/方法错统一 404
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # ② 路径遍历边界闸
        if full_path:
            try:
                candidate = (DIST / full_path).resolve()
                candidate.relative_to(DIST)
            except (ValueError, OSError):
                raise HTTPException(status_code=404)
            if candidate.is_file():
                return FileResponse(candidate)
            # ③ 带扩展名的缺失资源 → 404，不伪装成 HTML
            if Path(full_path).suffix:
                raise HTTPException(status_code=404)
        # 根路径 / 无扩展名前端路由 → SPA 壳
        return FileResponse(DIST / "index.html")
