"""TTS 客户端的抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TTSError(RuntimeError):
    """统一的 TTS 错误类型。"""


class TTSClient(ABC):
    """所有 TTS 后端的最小接口。"""

    @abstractmethod
    def synthesize(self, text: str) -> Optional[str]:
        """合成一句文本，返回临时 wav/mp3 文件路径；失败返回 None。"""

    def close(self) -> None:
        """释放底层资源（如子进程、HTTP 连接）。默认 no-op。"""
