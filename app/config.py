from typing import Literal

from pydantic import Field, model_validator
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

    # LLM 客户端实现：native（openai SDK 直连）或 langchain（ChatOpenAI 适配器）
    llm_backend: Literal["native", "langchain"] = "native"

    llm_max_tokens: int = 4096
    llm_timeout: float = 120.0

    # 图片页视觉识别：默认复用 ZHIYUAN_LLM_*（需模型支持视觉输入，如 step-3.7-flash）；
    # vision_max_pages 限制单个文档的识别请求数，控制 API 成本
    vision_model: str = ""
    vision_max_pages: int = Field(default=20, gt=0)

    # Embedding（OpenAI 兼容接口，URL+key 齐全即启用）
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = Field(default=1024, gt=0, le=65536)

    # Embedding 客户端实现：native（httpx 直连）或 langchain（OpenAIEmbeddings 适配器）
    embedding_backend: Literal["native", "langchain"] = "native"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "zhiyuan_chunks"

    # Postgres
    database_url: str = "postgresql+asyncpg://zhiyuan:zhiyuan_dev@localhost:5432/zhiyuan"

    # 摄入管线
    chunk_size: int = Field(default=500, gt=0, le=100_000)
    chunk_overlap: int = Field(default=50, ge=0, le=99_999)

    # 检索与重排
    # 向量召回条数（粗排）与重排后注入生成上下文的条数（精排）
    retrieval_top_k: int = Field(default=20, gt=0, le=1000)
    rerank_top_k: int = Field(default=5, gt=0, le=100)
    # 重排融合权重：final = vector_weight * 归一化向量分 + keyword_weight * 关键词命中率
    # 依据：向量分（余弦相似度）与关键词命中率都在 [0,1]，但真实分布差异大
    # （余弦相似度集中在 0.5~0.8，关键词命中率常落在 0~0.4），直接加权会让
    # 向量分主导——故先对候选项做 min-max 归一化再融合。默认 0.7/0.3 偏重语义，
    # 关键词作为纠偏项（专有名词、精确术语场景可调高 keyword_weight）。
    rerank_vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    rerank_keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    # 中文二元组过滤：仅在候选语料中出现过的 2-gram 参与打分，
    # 避免「档摄」「入失」这类跨词边界的假二元组稀释真实关键词权重。
    rerank_filter_bigrams: bool = True

    # 重排实现：keyword（默认，纯本地计算，无外部依赖）
    # 或 model（调用交叉编码器，精度更高，每次查询多一次模型推理）
    rerank_backend: Literal["keyword", "model"] = "keyword"
    # 模型重排走通用的 POST {base_url}/rerank 形状
    # （Cohere / Jina / SiliconFlow / TEI / Xinference 均实现该形状）。
    # 三者齐全且 backend=model 时启用；未配齐则启动时告警并降级为关键词重排。
    # 调用失败同样降级——重排是可选增强，不应让整条问答链路 500。
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""
    rerank_timeout: float = 30.0

    # 上传限制。接口按块读取，因此不会因为恶意 Content-Length 或大文件耗尽内存。
    max_upload_size: int = Field(default=50 * 1024 * 1024, gt=0, le=5 * 1024 * 1024 * 1024)

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

    @model_validator(mode="after")
    def validate_ingestion_settings(self) -> "Settings":
        """校验分块参数之间的关系，避免 splitter 运行时失败或死循环。"""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self

    @model_validator(mode="after")
    def validate_rerank_weights(self) -> "Settings":
        """重排权重需要构成有效凸组合，否则归一化分数不是加权平均。"""
        total = self.rerank_vector_weight + self.rerank_keyword_weight
        if total <= 0:
            raise ValueError("rerank_vector_weight + rerank_keyword_weight must be > 0")
        return self

    @model_validator(mode="after")
    def validate_rerank_top_k(self) -> "Settings":
        """精排条数不能超过召回条数，否则重排没有意义。"""
        if self.rerank_top_k > self.retrieval_top_k:
            raise ValueError("rerank_top_k must be <= retrieval_top_k")
        return self

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

    @property
    def rerank_model_configured(self) -> bool:
        """Whether all settings required by the model reranker exist."""
        return all(
            (
                self.rerank_base_url.strip(),
                self.rerank_api_key.strip(),
                self.rerank_model.strip(),
            )
        )

    @property
    def jwt_is_default_secret(self) -> bool:
        """jwt_secret 是否仍为不安全的默认值。"""
        return self.jwt_secret == "zhiyuan-dev-secret-change-in-production"


settings = Settings()
