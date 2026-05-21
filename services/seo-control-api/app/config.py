from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PatentZoom SEO Control API"
    database_url: str = "sqlite:///./services/seo-control-api/patentzoom_seo.db"
    redis_url: str = "redis://localhost:6379/0"
    worker_service_dir: str = str(Path(__file__).resolve().parents[2] / "seo-worker")
    worker_node_path: str | None = None
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_prefix="SEO_",
        extra="ignore",
    )


settings = Settings()

