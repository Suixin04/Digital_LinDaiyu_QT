"""环境变量驱动的配置入口。

集中处理 LLM / Embedding / TTS / ASR 等服务的开关与凭据，
便于在 CLI、测试、Qt UI 中复用同一份配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # 没装 python-dotenv 也无所谓，env 仍可由 shell 注入。
    pass


def _clean_env(name: str) -> str | None:
    """读取环境变量并去掉空白；空字符串视为未设置。"""
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def env_flag(name: str, default: bool = True) -> bool:
    """读取布尔型开关。常见的 0/false/no/off/disabled 视为关闭。"""
    value = _clean_env(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off", "disabled"}


# --------------------------------------------------------------------------- #
# Chat LLM
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChatModelConfig:
    """LLM 调用所需的最小配置。"""

    api_key: str | None
    model: str
    base_url: str

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)


def get_chat_model_config() -> ChatModelConfig:
    """优先取 CHAT_*，回退到 DEEPSEEK_* / OPENAI_*。"""
    api_key = (
        _clean_env("CHAT_API_KEY")
        or _clean_env("DEEPSEEK_API_KEY")
        or _clean_env("OPENAI_API_KEY")
    )
    model = (
        _clean_env("CHAT_MODEL")
        or _clean_env("DEEPSEEK_MODEL")
        or "deepseek-v4-flash"
    )
    base_url = (
        _clean_env("CHAT_BASE_URL")
        or _clean_env("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    )
    return ChatModelConfig(api_key=api_key, model=model, base_url=base_url)


# --------------------------------------------------------------------------- #
# Agent / DeepSeek tool calling
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentConfig:
    """DeepSeek 原生工具调用与思考模式配置。"""

    enable_tool_calls: bool
    max_tool_rounds: int
    enable_thinking: bool
    reasoning_effort: str
    stream_delay_ms: int


def get_agent_config() -> AgentConfig:
    try:
        max_tool_rounds = int(_clean_env("DIGITAL_LDY_MAX_TOOL_ROUNDS") or "4")
    except ValueError:
        max_tool_rounds = 4
    max_tool_rounds = max(1, min(8, max_tool_rounds))

    try:
        stream_delay_ms = int(_clean_env("DIGITAL_LDY_STREAM_DELAY_MS") or "10")
    except ValueError:
        stream_delay_ms = 10
    stream_delay_ms = max(0, min(80, stream_delay_ms))

    effort = (_clean_env("DEEPSEEK_REASONING_EFFORT") or "high").lower()
    if effort not in {"high", "max"}:
        effort = "high"

    return AgentConfig(
        enable_tool_calls=env_flag("DIGITAL_LDY_ENABLE_TOOL_CALLS", True),
        max_tool_rounds=max_tool_rounds,
        enable_thinking=env_flag("DEEPSEEK_THINKING", True),
        reasoning_effort=effort,
        stream_delay_ms=stream_delay_ms,
    )


# --------------------------------------------------------------------------- #
# 通用：DashScope
# --------------------------------------------------------------------------- #


def get_dashscope_api_key() -> str | None:
    """读取 DashScope 凭据；同时兼容旧的 ALIYUN_API_KEY 名称。"""
    return _clean_env("DASHSCOPE_API_KEY") or _clean_env("ALIYUN_API_KEY")


def get_dashscope_base_url() -> str:
    return _clean_env("DASHSCOPE_BASE_URL") or (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EmbeddingConfig:
    """决定使用云端还是本地嵌入模型。

    backend:
      - "dashscope" : 使用 DashScope text-embedding-vX（需要 API key）
      - "fastembed" : 本地 ONNX 模型（首次会下载 ~90MB）
      - "auto"      : 有 DashScope key 走云端，否则走本地
    """

    backend: str
    model: str


def get_embedding_config() -> EmbeddingConfig:
    backend = (_clean_env("EMBEDDING_BACKEND") or "auto").lower()
    if backend == "auto":
        backend = "dashscope" if get_dashscope_api_key() else "fastembed"
    if backend == "dashscope":
        model = _clean_env("DASHSCOPE_EMBEDDING_MODEL") or "text-embedding-v3"
    else:
        model = _clean_env("FASTEMBED_MODEL") or "BAAI/bge-small-zh-v1.5"
    return EmbeddingConfig(backend=backend, model=model)


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TTSConfig:
    """选择 TTS 后端。

    backend:
      - "gpt_sovits" : 本地 GPT-SoVITS HTTP 服务（高保真音色克隆，需本地模型）
      - "cosyvoice"  : DashScope CosyVoice 云端（零部署，3-10s 参考音克隆）
      - "none"       : 关闭语音
    """

    backend: str
    voice: str  # CosyVoice 专用：发音人或 zero-shot voice id


def get_tts_config() -> TTSConfig:
    backend = (_clean_env("TTS_BACKEND") or "gpt_sovits").lower()
    voice = _clean_env("COSYVOICE_VOICE") or "longxiaochun"
    return TTSConfig(backend=backend, voice=voice)
