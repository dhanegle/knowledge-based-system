"""视觉语言模型客户端：把文档图片页发给 OpenAI 兼容 VLM 提取文字。

默认复用 ZHIYUAN_LLM_* 配置（step-3.7-flash 实测支持视觉输入），
可用 ZHIYUAN_VISION_MODEL 单独指定视觉模型。识别失败返回 None，
由调用方决定是否保留"未提取"标注——不因单页识别失败拖垮摄入。
"""

from __future__ import annotations

import base64

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger("app.vision")

EXTRACTION_PROMPT = (
    "你是文档数字化助手。请完整提取图片中的全部文字内容，"
    "保持原有阅读顺序与结构（标题、列表照抄，表格转成文本行，单元格用 | 分隔）。"
    "如果图片包含图表、示意图或流程图，在文字之后用一段话描述其展示的内容。"
    "只输出提取和描述的结果，不要添加任何评论。"
)


class VisionClient:
    """OpenAI 兼容接口的视觉识别客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 120.0,
        max_tokens: int = 4096,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._http = http_client or httpx.AsyncClient(trust_env=False, timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    async def extract_text(
        self,
        image: bytes,
        mime: str,
        *,
        page_no: int | None = None,
    ) -> str | None:
        """识别单张图片，返回提取文本；失败或空结果返回 None。"""
        data_uri = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        hint = f"（这是文档的第 {page_no} 页）" if page_no else ""
        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT + hint},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            # 推理型模型（如 step-3.7-flash）会先思考，max_tokens 给足否则正文为空
            "max_tokens": self._max_tokens,
        }
        try:
            resp = await self._http.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"].get("content")
            return (content or "").strip() or None
        except Exception as e:
            logger.warning(
                "vision_extract_failed", page=page_no, model=self._model, error=str(e)
            )
            return None

    async def aclose(self) -> None:
        await self._http.aclose()


_client: VisionClient | None = None


def get_vision_client() -> VisionClient | None:
    """配置齐全才创建；未配置时返回 None，摄入管线降级为不识别。"""
    global _client
    if _client is not None:
        return _client
    if not settings.llm_configured:
        return None

    _client = VisionClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.vision_model or settings.llm_model,
        timeout=settings.llm_timeout,
        max_tokens=max(settings.llm_max_tokens, 2048),
    )
    return _client


def reset_vision_client() -> None:
    """重置单例，供测试使用。"""
    global _client
    _client = None
