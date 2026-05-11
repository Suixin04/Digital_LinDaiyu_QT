"""TTS 抽象与多后端实现。

提供：
    - TTSClient 抽象基类
    - GPTSoVITSClient：本地 GPT-SoVITS HTTP 服务（高保真音色克隆）
    - CosyVoiceClient：DashScope CosyVoice 云端（零部署）
    - get_tts_client() 工厂
"""

from __future__ import annotations

from .base import TTSClient, TTSError
from .factory import get_tts_client

__all__ = ["TTSClient", "TTSError", "get_tts_client"]
