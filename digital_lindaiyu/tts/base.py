"""TTS 客户端的抽象接口。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional


class TTSError(RuntimeError):
    """统一的 TTS 错误类型。"""


# 中/英括号内的旁白（动作神态描述），不应被朗读。
# 允许里面再嵌一层括号（非贪婪 + 跨行）。
_STAGE_DIRECTION_RE = re.compile(r"[（(][^（）()]*[）)]", flags=re.DOTALL)

# 句首多余的标点 / 空白（流式时常残留上一句的句号、引号等）
_LEADING_NOISE_RE = re.compile(r"^[\s。，、；：！？.,;:!?…\-—\"\'""''`]+")


def clean_for_tts(text: str) -> str:
    """剥掉不该朗读的内容，返回干净的合成文本。

    - 去掉成对的 ``（...）`` / ``(...)`` 旁白
    - 反复套用以消除嵌套
    - 去掉句首遗留的标点和空白
    """
    if not text:
        return ""
    prev = None
    while prev != text:
        prev = text
        text = _STAGE_DIRECTION_RE.sub("", text)
    text = _LEADING_NOISE_RE.sub("", text)
    return text.strip()


class TTSClient(ABC):
    """所有 TTS 后端的最小接口。"""

    @abstractmethod
    def synthesize(self, text: str) -> Optional[str]:
        """合成一句文本，返回临时 wav/mp3 文件路径；失败返回 None。"""

    def close(self) -> None:
        """释放底层资源（如子进程、HTTP 连接）。默认 no-op。"""
