"""基于 openai SDK 的 provider,供 Kimi / OpenAI 复用。

Kimi(aiping.cn)与 OpenAI 都兼容 openai Chat Completions 接口,
差异仅在 base_url / model / api_key,由 ProviderConfig 提供。
"""
from __future__ import annotations

from ..config import ProviderConfig
from .base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容接口 provider 基类。"""

    def __init__(self, cfg: ProviderConfig):
        super().__init__(cfg)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI(
                api_key=self.cfg.api_key,
                base_url=self.cfg.base_url,
                timeout=self.cfg.timeout,
                max_retries=0,  # 重试由 base 层统一处理
            )
        return self._client

    # 子类可覆盖:传给 API 的额外 body 参数(如 Kimi 的 enable_thinking)
    extra_body: dict = {}

    def _translate_one(self, text: str, system_prompt: str) -> str:
        kwargs = dict(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=4000,
        )
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class KimiProvider(OpenAICompatProvider):
    name = "kimi"
    extra_body = {"enable_thinking": False}


class OpenAIProvider(OpenAICompatProvider):
    name = "openai"
