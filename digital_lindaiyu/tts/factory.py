"""根据配置创建合适的 TTS 客户端。"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import TTSConfig, get_tts_config
from .base import TTSClient, TTSError

logger = logging.getLogger(__name__)


def get_tts_client(config: Optional[TTSConfig] = None) -> Optional[TTSClient]:
    """根据 ``TTSConfig`` 创建客户端；失败时返回 None。"""
    cfg = config or get_tts_config()
    backend = cfg.backend
    if backend == "none":
        return None
    try:
        if backend == "gpt_sovits":
            from .gpt_sovits import GPTSoVITSClient

            return GPTSoVITSClient()
        if backend == "cosyvoice":
            from .cosyvoice import CosyVoiceClient

            return CosyVoiceClient(voice=cfg.voice)
    except TTSError as e:
        logger.warning("TTS 后端 %s 初始化失败: %s", backend, e)
        return None
    raise ValueError(f"未知的 TTS 后端: {backend}")
