"""provider 注册表:按名字构造对应 LLMProvider。"""
from __future__ import annotations

from ..config import Config, load_config
from .base import LLMProvider
from .openai import KimiProvider, OpenAIProvider

_REGISTRY = {
    "kimi": KimiProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str | None = None, config: Config | None = None) -> LLMProvider:
    """构造 provider。name 为空则用配置里的 default_provider。"""
    config = config or load_config()
    name = name or config.default_provider
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"未知 provider {name!r};可用: {list(_REGISTRY)}")
    return cls(config.provider(name))


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    """注册自定义 provider(扩展点)。"""
    _REGISTRY[name] = cls
