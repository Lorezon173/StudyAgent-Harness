from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "StudyAgent"
    app_version: str = "0.1.0"
    debug: bool = True
    database_url: str = "sqlite+aiosqlite:///./study_agent.db"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # RAG & Embedding 配置（阶段 A：真向量检索）
    rag_backend: str = "fake"  # "fake" | "pgvector"，默认 fake 保持测试兼容
    embedding_model: str = "doubao-embedding-vision"  # 火山引擎方舟 embedding 模型
    embedding_dim: int = 2048  # doubao-embedding-vision 默认维度

    # JWT 配置（批次三 P0-③）
    jwt_secret_key: str = "dev-secret-change-me-in-production"
    jwt_expire_minutes: int = 1440  # 24 小时（dev 环境；上 prod 前需重审）

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8",
                    "extra": "ignore"}


settings = Settings()
