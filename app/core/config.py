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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8",
                    "extra": "ignore"}


settings = Settings()
