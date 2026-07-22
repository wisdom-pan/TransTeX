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
            import httpx
            import openai

            # 自定义 httpx 传输:连接级重试 + 短 keepalive。
            # Kimi(aiping.cn)偶发 "EOF occurred in violation of protocol (_ssl.c:...)"
            # 多因连接池复用了服务端已关闭的陈旧 SSL 连接;transport retries 在连接
            # 建立阶段重试,短 keepalive_expiry 让空闲连接尽快被丢弃、不再复用陈旧连接。
            # 注意 httpx 0.28 的参数归属:keepalive_expiry 是 httpx.Limits 的字段,
            # 不能裸传给 httpx.Client 或 HTTPTransport;且用自定义 transport 时,
            # limits 必须塞进 HTTPTransport 才对该连接池生效(传给 Client 会被忽略)。
            # 早期写法把 keepalive_expiry 塞给 HTTPTransport,会抛 TypeError,导致
            # 每段翻译全失败、回退原文(译文=英文)。
            limits = httpx.Limits(keepalive_expiry=5.0)
            transport = httpx.HTTPTransport(retries=3, limits=limits)
            http_client = httpx.Client(
                transport=transport,
                timeout=self.cfg.timeout,
            )
            self._client = openai.OpenAI(
                api_key=self.cfg.api_key,
                base_url=self.cfg.base_url,
                timeout=self.cfg.timeout,
                max_retries=0,  # 应用层重试由 base 层统一处理
                http_client=http_client,
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
