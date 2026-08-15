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

    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
