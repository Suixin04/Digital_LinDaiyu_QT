"""把 ChatEngine 包装成 QThread，用于 Qt UI。

TTS 设计要点：
- 服务端是单 GPU 串行处理，客户端再用多线程只会让短句越过长句先返回，
  导致 ``audio_ready`` 信号乱序、UI 队列错位（听感上像"吞句"）。
- 因此这里改用 **单条 FIFO + 专用工作线程**：句子按 ChatEngine 切句顺序入队，
  工作线程按序合成、按序通过信号发射，UI 端无需关心顺序。
- 工作线程在 ``run()`` 结束时收一个哨兵优雅退出。
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal

from digital_lindaiyu.chat import ChatEngine
from digital_lindaiyu.tts import TTSClient
from digital_lindaiyu.tts.base import clean_for_tts

logger = logging.getLogger(__name__)

_SENTINEL = object()


class ChatWorker(QThread):
    """异步执行一次对话；通过信号把流式片段/日志/音频路径传给 UI。"""

    message_received = Signal(str)   # LLM 流式片段
    chat_completed = Signal(str)     # 整段回复完成
    audio_ready = Signal(str)        # 单个音频文件路径（严格按句序）
    log_signal = Signal(str)         # 调试日志

    def __init__(
        self,
        engine: ChatEngine,
        user_message: str,
        thread_id: str = "default",
        tts_client: Optional[TTSClient] = None,
        tts_workers: int = 1,  # 保留参数兼容；当前实现固定使用单线程串行
    ) -> None:
        super().__init__()
        self.engine = engine
        self.user_message = user_message
        self.thread_id = thread_id
        self.tts_client = tts_client
        self._tts_queue: Optional["queue.Queue[object]"] = None
        self._tts_thread: Optional[threading.Thread] = None
        if tts_client is not None:
            self._tts_queue = queue.Queue()
            self._tts_thread = threading.Thread(
                target=self._tts_loop, name="ChatWorker-TTS", daemon=True
            )
            self._tts_thread.start()

    # --------------------------- callbacks --------------------------- #

    def _on_chunk(self, piece: str) -> None:
        self.message_received.emit(piece)

    def _on_sentence(self, sentence: str) -> None:
        if self._tts_queue is None:
            return
        spoken = clean_for_tts(sentence)
        # 旁白被剥掉后可能只剩 1~2 字标点，太短没必要送 TTS
        if len(spoken) < 2:
            return
        self._tts_queue.put(spoken)

    # ----------------------- TTS 工作线程 ----------------------- #

    def _tts_loop(self) -> None:
        """专用串行线程：按入队顺序合成并按序 emit ``audio_ready``。"""
        assert self._tts_queue is not None
        while True:
            item = self._tts_queue.get()
            if item is _SENTINEL:
                return
            sentence = item  # type: ignore[assignment]
            try:
                path = self.tts_client.synthesize(sentence)  # type: ignore[union-attr]
            except Exception as e:  # noqa: BLE001
                logger.warning("TTS 合成异常: %s", e)
                self.log_signal.emit(f"TTS 合成异常: {e}")
                continue
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
            # 等待 TTS 队列把剩余句子合成完，再退出线程
            if self._tts_queue is not None:
                self._tts_queue.put(_SENTINEL)
            if self._tts_thread is not None:
                self._tts_thread.join(timeout=120)
