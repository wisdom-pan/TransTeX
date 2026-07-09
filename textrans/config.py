"""TexTrans 全局配置:环境变量 + 可选 config.toml。

优先级:显式参数 > 环境变量 > config.toml > 内置默认。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # Python 3.11+ 内置;更低版本可选依赖 tomli
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore


@dataclass
class ProviderConfig:
    """单个 LLM provider 的连接配置。"""

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    rate_limit: float = 5.0  # 每秒最大请求数
    max_retries: int = 5
    timeout: int = 120


# 内置默认 provider 配置。api_key 必须通过环境变量提供(KIMI_API_KEY / OPENAI_API_KEY)。
_DEFAULT_PROVIDERS: dict[str, ProviderConfig] = {
    "kimi": ProviderConfig(
        # 密钥请通过 KIMI_API_KEY 环境变量注入,切勿硬编码到源码。
        api_key="",
        base_url="https://aiping.cn/api/v1",
        model="Kimi-K2.6",
    ),
    "openai": ProviderConfig(
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    ),
}


# 项目根目录(textrans/ 的上一级)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 默认水印图片:项目根目录下的 dt.l.png
_DEFAULT_WATERMARK = _PROJECT_ROOT / "dt.l.png"


def _default_workdir() -> Path:
    r"""默认工作目录(绝对路径)。

    绝对化很重要:后端可能从任意目录启动(uvicorn/systemd/docker),
    若用相对路径 ./textrans_workdir,则不同 CWD 会指向不同目录,
    导致数据库/历史记录"看起来丢了"。故锁定到项目根下的绝对路径。
    环境变量 TEXTRANS_WORKDIR 若为相对路径也解析为绝对。
    """
    raw = os.getenv("TEXTRANS_WORKDIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return _PROJECT_ROOT / "textrans_workdir"


@dataclass
class Config:
    default_provider: str = "kimi"
    providers: dict[str, ProviderConfig] = field(
        default_factory=lambda: {k: ProviderConfig(**vars(v)) for k, v in _DEFAULT_PROVIDERS.items()}
    )
    workdir: Path = field(default_factory=_default_workdir)
    watermark_path: Path = _DEFAULT_WATERMARK

    def provider(self, name: Optional[str] = None) -> ProviderConfig:
        name = name or self.default_provider
        pc = self.providers.get(name)
        if pc is None:
            raise KeyError(f"未知 provider: {name!r};可用: {list(self.providers)}")
        return pc


def _apply_env(cfg: Config) -> None:
    """用环境变量覆盖敏感/常改配置。"""
    if os.getenv("TEXTRANS_PROVIDER"):
        cfg.default_provider = os.environ["TEXTRANS_PROVIDER"]

    if os.getenv("TEXTRANS_WATERMARK"):
        cfg.watermark_path = Path(os.environ["TEXTRANS_WATERMARK"])

    # Kimi:兼容既有项目的 KIMI_API_KEY / KIMI_BASE_URL
    kimi = cfg.providers["kimi"]
    kimi.api_key = os.getenv("KIMI_API_KEY", kimi.api_key)
    kimi.base_url = os.getenv("KIMI_BASE_URL", kimi.base_url)

    openai_cfg = cfg.providers["openai"]
    openai_cfg.api_key = os.getenv("OPENAI_API_KEY", openai_cfg.api_key)
    openai_cfg.base_url = os.getenv("OPENAI_BASE_URL", openai_cfg.base_url)


def _load_dotenv() -> None:
    """加载项目根目录的 .env 到 os.environ(不覆盖已存在的真实环境变量)。

    代码只读 os.getenv,若不主动加载 .env,则文件中的 KIMI_API_KEY 等
    不会生效,导致请求带空密钥 → 401 unauthorized。python-dotenv 缺失时静默跳过。
    """
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:  # pragma: no cover
        return
    # config.py 在 textrans/ 下,.env 在其上一级项目根目录
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)


def load_config(path: Optional[Path] = None) -> Config:
    """加载配置。若存在 config.toml 则合并。"""
    _load_dotenv()
    cfg = Config()

    toml_path = path or Path("config.toml")
    if tomllib is not None and toml_path.exists():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        if "default_provider" in data:
            cfg.default_provider = data["default_provider"]
        for name, pdata in (data.get("providers") or {}).items():
            base = cfg.providers.get(name, ProviderConfig())
            for k, v in pdata.items():
                setattr(base, k, v)
            cfg.providers[name] = base
        if "workdir" in data:
            cfg.workdir = Path(data["workdir"])

    _apply_env(cfg)
    return cfg
