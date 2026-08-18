from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ZHIYUAN_",
        extra="ignore",
    )

    app_name: str = "知源"
    debug: bool = False

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    llm_max_tokens: int = 4096
    llm_timeout: float = 120.0

    # Embedding（暂未接入，等用户提供 URL+key）
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 1024

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "zhiyuan_chunks"

    # Postgres
    database_url: str = "postgresql+asyncpg://zhiyuan:zhiyuan_dev@localhost:5432/zhiyuan"

    # 摄入管线
    chunk_size: int = 500
    chunk_overlap: int = 50

    # 可观测性
    langfuse_base_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # 鉴权
    jwt_secret: str = "zhiyuan-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 小时

    # 缓存
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 3600  # 1 小时

    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def llm_configured(self) -> bool:
        """Whether all settings required by the OpenAI-compatible client exist."""
        return all(
            (
                self.llm_base_url.strip(),
                self.llm_api_key.strip(),
                self.llm_model.strip(),
            )
        )

    @property
    def embedding_configured(self) -> bool:
        """Whether all settings required by the embedding service exist."""
        return all(
            (
                self.embedding_base_url.strip(),
                self.embedding_api_key.strip(),
                self.embedding_model.strip(),
            )
        )


settings = Settings()
