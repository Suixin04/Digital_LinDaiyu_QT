"""TTS 客户端的抽象接口。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional


class TTSError(RuntimeError):
    """统一的 TTS 错误类型。"""


# 句首多余的标点 / 空白（流式时常残留上一句的句号、引号等）
_LEADING_NOISE_RE = re.compile(r"^[\s。，、；：！？.,;:!?…\-—\"'“”‘’`）)\]］】]+")

_STAGE_OPEN_TO_CLOSE = {
    "(": ")",
    "（": "）",
    "[": "]",
    "［": "］",
    "【": "】",
}
_STAGE_CLOSES = set(_STAGE_OPEN_TO_CLOSE.values())


def _strip_stage_directions(text: str) -> str:
    """Remove bracketed stage directions, including nested or unfinished spans."""
    result: list[str] = []
    stack: list[str] = []
    for ch in text:
        if ch in _STAGE_OPEN_TO_CLOSE:
            stack.append(_STAGE_OPEN_TO_CLOSE[ch])
            continue
        if stack:
            if ch in _STAGE_OPEN_TO_CLOSE:
                stack.append(_STAGE_OPEN_TO_CLOSE[ch])
            elif ch == stack[-1]:
                stack.pop()
            elif ch in _STAGE_CLOSES:
                stack.pop()
            continue
        if ch in _STAGE_CLOSES:
            continue
        result.append(ch)
    return "".join(result)


def clean_for_tts(text: str) -> str:
    """剥掉不该朗读的内容，返回干净的合成文本。

    - 去掉 ``（...）`` / ``(...)`` / ``【...】`` / ``[...]`` 旁白
    - 支持嵌套；未闭合括号会从开括号处截断，避免朗读半句旁白
    - 去掉句首遗留的标点和空白
    """
    if not text:
        return ""
    text = _strip_stage_directions(text)
    text = _LEADING_NOISE_RE.sub("", text)
    return text.strip()


class TTSClient(ABC):
    """所有 TTS 后端的最小接口。"""

    @abstractmethod
    def synthesize(self, text: str) -> Optional[str]:
        """合成一句文本，返回临时 wav/mp3 文件路径；失败返回 None。"""

    def close(self) -> None:
        """释放底层资源（如子进程、HTTP 连接）。默认 no-op。"""
