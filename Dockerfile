# ===== Stage 1: 前端构建（React + Vite → web/dist）=====
# 产物由 app/main.py:40 的 web/dist 检测分支自动挂载，FastAPI 同源伺服
FROM node:20-alpine AS frontend
WORKDIR /build
# 先拷 lock，利用 npm ci 缓存层（lockfile 存在）
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# 产物：/build/dist（web/vite.config.ts 的 outDir: "dist"）
RUN npm run build

# ===== Stage 2: 后端依赖（uv sync 装 .venv）=====
FROM python:3.11-slim AS backend
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv
WORKDIR /app
# 先仅凭 pyproject.toml 装依赖（利用缓存，源码变动不重装）
COPY pyproject.toml uv.lock* ./
RUN uv sync --extra rag --no-dev --no-install-project
# 再拷源码并装项目本身
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
RUN uv sync --extra rag --no-dev

# ===== Stage 3: runtime（精简运行镜像）=====
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
# psycopg[binary] 自带 libpq；uvicorn[standard] 走 manylinux wheel —— 无需额外系统包
COPY --from=backend /app/.venv /app/.venv
COPY --from=backend /app/app ./app
COPY --from=backend /app/alembic.ini /app/alembic.ini
COPY --from=backend /app/alembic ./alembic
# 前端产物落 /app/web/dist（对齐 main.py 相对工作目录的 web/dist 检测）
COPY --from=frontend /build/dist ./web/dist
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
# 启动即迁移（单机自愈），再起 uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
