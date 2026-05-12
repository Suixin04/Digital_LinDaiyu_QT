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


# --------------------------------------------------------------------------- #
# GPT-SoVITS (本地 api_v2.py)
# --------------------------------------------------------------------------- #


# 默认参考音 = 训练样本 17.MP3 (5.67s，落在 GPT-SoVITS 要求的 3~10s 区间)。
# 转写见 GPT-SoVITS/output/asr_opt/samples.list。
DEFAULT_REF_AUDIO = "resources/samples/17.MP3"
DEFAULT_PROMPT_TEXT = "别扫大家的兴。舅舅要是叫你，就说姨妈留你吃酒呢。"


@dataclass(frozen=True)
class GPTSoVITSConfig:
    """启动本地 GPT-SoVITS api_v2.py 并合成语音所需的全部参数。

    所有路径如果是相对路径，都解析自项目根目录。
    weights 路径在调用 ``/set_gpt_weights`` / ``/set_sovits_weights`` 时
    要相对于 ``project_dir``（也就是 api_v2 的工作目录）。
    """

    project_dir: str         # GPT-SoVITS 源码所在目录
    python_exe: str          # 启动 api_v2 所用 Python 解释器
    host: str
    port: int
    config_file: str         # 相对 project_dir，传给 api_v2 的 -c
    gpt_weights: str         # 相对 project_dir
    sovits_weights: str      # 相对 project_dir
    ref_audio: str           # 绝对路径或相对项目根
    prompt_text: str
    text_lang: str
    prompt_lang: str
    auto_start: bool
    ffmpeg_bin: str | None   # 启动子进程时要 prepend 到 PATH 的 FFmpeg bin 目录
    startup_timeout: int     # 等待 api_v2 起来的秒数

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def get_gpt_sovits_config() -> GPTSoVITSConfig:
    project_dir = _clean_env("GPT_SOVITS_DIR") or "GPT-SoVITS"

    default_python = os.path.join(
        project_dir, ".venv-gsv", "Scripts", "python.exe"
    )
    if not os.path.exists(default_python):
        # 非 Windows 或没装专用环境时回退到当前解释器
        import sys as _sys

        default_python = _sys.executable
    python_exe = _clean_env("GPT_SOVITS_PYTHON") or default_python

    try:
        port = int(_clean_env("GPT_SOVITS_PORT") or "9880")
    except ValueError:
        port = 9880

    try:
        startup_timeout = int(_clean_env("GPT_SOVITS_STARTUP_TIMEOUT") or "60")
    except ValueError:
        startup_timeout = 60

    default_ffmpeg = os.path.join(project_dir, "runtime", "ffmpeg", "bin")
    ffmpeg_bin = _clean_env("GPT_SOVITS_FFMPEG_BIN") or (
        default_ffmpeg if os.path.isdir(default_ffmpeg) else None
    )

    return GPTSoVITSConfig(
        project_dir=project_dir,
        python_exe=python_exe,
        host=_clean_env("GPT_SOVITS_HOST") or "127.0.0.1",
        port=port,
        config_file=_clean_env("GPT_SOVITS_CONFIG")
        or "GPT_SoVITS/configs/tts_infer.yaml",
        gpt_weights=_clean_env("GPT_SOVITS_GPT_WEIGHTS")
        or "GPT_weights_v2ProPlus/LinDaiyu-e15.ckpt",
        sovits_weights=_clean_env("GPT_SOVITS_SOVITS_WEIGHTS")
        or "SoVITS_weights_v2ProPlus/LinDaiyu_e8_s720.pth",
        ref_audio=_clean_env("GPT_SOVITS_REF_AUDIO") or DEFAULT_REF_AUDIO,
        prompt_text=_clean_env("GPT_SOVITS_PROMPT_TEXT") or DEFAULT_PROMPT_TEXT,
        text_lang=_clean_env("GPT_SOVITS_TEXT_LANG") or "zh",
        prompt_lang=_clean_env("GPT_SOVITS_PROMPT_LANG") or "zh",
        auto_start=env_flag("GPT_SOVITS_AUTO_START", True),
        ffmpeg_bin=ffmpeg_bin,
        startup_timeout=startup_timeout,
    )
