"""把 ChatEngine 包装成 QThread，用于 Qt UI。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PySide6.QtCore import QThread, Signal

from digital_lindaiyu.chat import ChatEngine
from digital_lindaiyu.tts import TTSClient

logger = logging.getLogger(__name__)


class ChatWorker(QThread):
    """异步执行一次对话；通过信号把流式片段/日志/音频路径传给 UI。"""

    message_received = Signal(str)   # LLM 流式片段
    chat_completed = Signal(str)     # 整段回复完成
    audio_ready = Signal(str)        # 单个音频文件路径
    log_signal = Signal(str)         # 调试日志

    def __init__(
        self,
        engine: ChatEngine,
        user_message: str,
        thread_id: str = "default",
        tts_client: Optional[TTSClient] = None,
        tts_workers: int = 3,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.user_message = user_message
        self.thread_id = thread_id
        self.tts_client = tts_client
        self._tts_pool: Optional[ThreadPoolExecutor] = (
            ThreadPoolExecutor(max_workers=tts_workers) if tts_client else None
        )

    # --------------------------- callbacks --------------------------- #

    def _on_chunk(self, piece: str) -> None:
        self.message_received.emit(piece)

    def _on_sentence(self, sentence: str) -> None:
        if not self._tts_pool or not sentence.strip():
            return
        future = self._tts_pool.submit(self._synthesize, sentence)
        future.add_done_callback(self._tts_done)

    def _synthesize(self, sentence: str) -> Optional[str]:
        if self.tts_client is None:
            return None
        try:
            return self.tts_client.synthesize(sentence)
        except Exception as e:
            logger.warning("TTS 合成异常: %s", e)
            return None

    def _tts_done(self, future) -> None:
        try:
            path = future.result()
        except Exception as e:
            self.log_signal.emit(f"TTS 任务异常: {e}")
            return
        if path:
            self.audio_ready.emit(path)

    # ---------------------------- thread ---------------------------- #

    def run(self) -> None:
        # 把 engine 的 log 接到 Qt 信号
        self.engine.log = self.log_signal.emit
        try:
            response = self.engine.stream(
                self.user_message,
                thread_id=self.thread_id,
                on_chunk=self._on_chunk,
                on_sentence=self._on_sentence,
            )
            self.chat_completed.emit(response)
        except Exception as e:
            self.log_signal.emit(f"对话处理出错: {e}")
            self.message_received.emit(f"对话处理出错: {e}")
            self.chat_completed.emit("")
        finally:
            if self._tts_pool is not None:
                self._tts_pool.shutdown(wait=False)
