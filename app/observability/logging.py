"""结构化日志配置（structlog）。

输出 JSON 格式日志，包含时间戳、日志级别、事件名、请求 ID。
开发模式用彩色控制台输出，生产模式用 JSON。
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings


def setup_logging() -> None:
    """初始化 structlog + 标准库 logging 集成。"""
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.debug:
        # 开发模式：彩色控制台
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        log_level = logging.DEBUG
    else:
        # 生产模式：JSON
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
        log_level = logging.INFO

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 把标准库 logging 也桥接到 structlog
    logging.basicConfig(
        level=log_level,
        stream=sys.stdout,
        format="%(message)s",
        force=True,
    )

    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.get_logger("app").info(
        "logging_initialized",
        debug=settings.debug,
        app=settings.app_name,
    )
