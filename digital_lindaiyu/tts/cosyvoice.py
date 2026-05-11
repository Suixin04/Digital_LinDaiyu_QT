"""DashScope CosyVoice 2 客户端。

CosyVoice 是 2024-2025 阿里通义实验室开源 / 上云的 TTS，
支持 ``zero-shot voice clone``（3-10 秒参考音）与多种内置发音人，
特别适合需要稳定中文表演的角色对话场景。

文档: https://help.aliyun.com/zh/dashscope/developer-reference/cosyvoice
"""

from __future__ import annotations

import logging
import tempfile
from typing import Optional

from ..config import get_dashscope_api_key
from .base import TTSClient, TTSError

logger = logging.getLogger(__name__)

# 阿里官方内置发音人示例；可在 .env 中通过 COSYVOICE_VOICE 覆盖。
# 若需自定义角色音色，请在 DashScope 控制台先完成 zero-shot voice 注册。
DEFAULT_VOICE = "longxiaochun"
DEFAULT_MODEL = "cosyvoice-v2"


class CosyVoiceClient(TTSClient):
    """通过 dashscope SDK 调用 CosyVoice 合成中文语音。"""

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL,
    ) -> None:
        api_key = get_dashscope_api_key()
        if not api_key:
            raise TTSError("未设置 DASHSCOPE_API_KEY，无法使用 CosyVoice。")
        try:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizer
        except ImportError as e:  # pragma: no cover
            raise TTSError(
                "未安装 dashscope。请运行: uv pip install 'dashscope>=1.20'"
            ) from e
        dashscope.api_key = api_key
        self._SpeechSynthesizer = SpeechSynthesizer
        self.voice = voice
        self.model = model

    def synthesize(self, text: str) -> Optional[str]:
        try:
            synthesizer = self._SpeechSynthesizer(
                model=self.model, voice=self.voice
            )
            audio = synthesizer.call(text)
        except Exception as e:
            logger.warning("CosyVoice 合成失败: %s", e)
            return None
        if not audio:
            return None
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            return f.name
