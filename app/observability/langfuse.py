"""Langfuse 追踪集成（可选）。

当配置了 Langfuse 的 base_url + public_key + secret_key 时启用追踪。
未配置时降级为 structlog 日志记录。

追踪 RAG 查询的每个阶段：embed_query → vector_search → rerank → llm_generate
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger("app.trace")

_langfuse = None


def _init_langfuse():
    """惰性初始化 Langfuse 客户端。"""
    global _langfuse
    if _langfuse is not None:
        return _langfuse

    if not (settings.langfuse_base_url and settings.langfuse_public_key and settings.langfuse_secret_key):
        return None

    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            base_url=settings.langfuse_base_url,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        logger.info("langfuse_initialized", base_url=settings.langfuse_base_url)
    except ImportError:
        logger.warning("langfuse_not_installed")
        return None
    except Exception as e:
        logger.warning("langfuse_init_failed", error=str(e))
        return None

    return _langfuse


def trace_span(name: str):
    """追踪装饰器：记录函数耗时和输入输出。

    - 有 Langfuse 时上报到 Langfuse
    - 没有 Langfuse 时用 structlog 记录
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "trace_span",
                    span=name,
                    elapsed_ms=round(elapsed_ms, 2),
                    status="ok",
                )
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "trace_span",
                    span=name,
                    elapsed_ms=round(elapsed_ms, 2),
                    status="error",
                    error=str(e),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "trace_span",
                    span=name,
                    elapsed_ms=round(elapsed_ms, 2),
                    status="ok",
                )
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "trace_span",
                    span=name,
                    elapsed_ms=round(elapsed_ms, 2),
                    status="error",
                    error=str(e),
                )
                raise

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


_langchain_handler: Any | None = None
_langchain_handler_checked = False


def get_langchain_callback_handler():
    """返回 Langfuse 的 LangChain CallbackHandler，未配置或未安装时返回 None。

    供 LCEL 链路挂在 config 的 callbacks 上，整条链自动上报 trace。
    v3 的 CallbackHandler 只收 public_key，secret_key 和 host 走环境变量。
    """
    global _langchain_handler, _langchain_handler_checked
    if _langchain_handler_checked:
        return _langchain_handler
    _langchain_handler_checked = True

    if not (settings.langfuse_base_url and settings.langfuse_public_key and settings.langfuse_secret_key):
        return None

    try:
        import os

        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
        os.environ["LANGFUSE_HOST"] = settings.langfuse_base_url

        from langfuse.langchain import CallbackHandler

        _langchain_handler = CallbackHandler(public_key=settings.langfuse_public_key)
        logger.info("langfuse_langchain_handler_enabled", base_url=settings.langfuse_base_url)
    except ImportError:
        logger.warning("langfuse_not_installed")
        _langchain_handler = None
    except Exception as e:
        logger.warning("langfuse_handler_init_failed", error=str(e))
        _langchain_handler = None

    return _langchain_handler


def reset_langchain_callback_handler() -> None:
    """重置 handler 缓存。供测试或运行中修改 Langfuse 配置后调用。"""
    global _langchain_handler, _langchain_handler_checked
    _langchain_handler = None
    _langchain_handler_checked = False
