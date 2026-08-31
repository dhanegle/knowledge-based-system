"""Langfuse LangChain callback 助手测试。"""

import sys
import types

import app.observability.langfuse as obs_langfuse
from app.config import settings


def test_handler_is_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_base_url", "")
    obs_langfuse.reset_langchain_callback_handler()
    try:
        assert obs_langfuse.get_langchain_callback_handler() is None
    finally:
        obs_langfuse.reset_langchain_callback_handler()


def test_handler_constructed_when_configured(monkeypatch):
    created = {}

    class FakeHandler:
        def __init__(self, **kwargs):
            created.update(kwargs)

    fake_mod = types.ModuleType("langfuse.langchain")
    fake_mod.CallbackHandler = FakeHandler
    fake_pkg = types.ModuleType("langfuse")
    fake_pkg.langchain = fake_mod

    monkeypatch.setattr(settings, "langfuse_base_url", "https://lf.test")
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    # helper 会写这几个环境变量，先占位以便测试后恢复
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "keep")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "keep")
    monkeypatch.setenv("LANGFUSE_HOST", "keep")
    monkeypatch.setitem(sys.modules, "langfuse", fake_pkg)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", fake_mod)

    obs_langfuse.reset_langchain_callback_handler()
    try:
        handler = obs_langfuse.get_langchain_callback_handler()

        assert isinstance(handler, FakeHandler)
        assert created["public_key"] == "pk-test"
        import os

        assert os.environ["LANGFUSE_SECRET_KEY"] == "sk-test"
        assert os.environ["LANGFUSE_HOST"] == "https://lf.test"
    finally:
        obs_langfuse.reset_langchain_callback_handler()
