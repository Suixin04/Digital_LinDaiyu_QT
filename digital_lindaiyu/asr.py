"""DashScope Paraformer realtime ASR 封装。

设计上独立于 Qt：通过回调把识别到的文本回传给调用方。
Qt 层在 ``ui.worker`` 中再包一层 QThread + Signal。
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from .config import get_dashscope_api_key

logger = logging.getLogger(__name__)


class ASRSession:
    """一次性语音识别会话；调用 ``start``/``stop`` 控制生命周期。"""

    def __init__(self, on_text: Callable[[str], None]) -> None:
        api_key = get_dashscope_api_key()
        if not api_key:
            raise RuntimeError("未设置 DASHSCOPE_API_KEY，无法使用语音识别。")
        try:
            import dashscope
            from dashscope.audio.asr import (
                Recognition,
                RecognitionCallback,
                RecognitionResult,
            )
            import pyaudio
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 dashscope 或 pyaudio。请运行: "
                "uv pip install dashscope pyaudio"
            ) from e

        dashscope.api_key = api_key
        self._pyaudio = pyaudio
        self._on_text = on_text
        self._mic: Optional[object] = None
        self._stream: Optional[object] = None
        self._running = threading.Event()
        self._reader: Optional[threading.Thread] = None

        outer = self

        class _Callback(RecognitionCallback):  # type: ignore[misc]
            def on_open(self_inner) -> None:
                outer._mic = outer._pyaudio.PyAudio()
                outer._stream = outer._mic.open(
                    format=outer._pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=3200,
                )

            def on_close(self_inner) -> None:
                outer._close_audio()

            def on_event(self_inner, result: RecognitionResult) -> None:
                try:
                    sentence = result.get_sentence()
                    if sentence and sentence.get("text"):
                        outer._on_text(sentence["text"])
                except Exception as e:
                    logger.warning("处理 ASR 事件出错: %s", e)

        self._recognition = Recognition(
            model="paraformer-realtime-v2",
            format="pcm",
            sample_rate=16000,
            callback=_Callback(),
        )

    # --------------------------- lifecycle --------------------------- #

    def start(self) -> None:
        """启动识别；麦克风读取放到后台线程，避免阻塞调用方。"""
        self._running.set()
        self._recognition.start()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._running.clear()
        try:
            self._recognition.stop()
        finally:
            self._close_audio()
        if self._reader is not None:
            self._reader.join(timeout=2)

    # --------------------------- internals --------------------------- #

    def _pump(self) -> None:
        while self._running.is_set():
            stream = self._stream
            if stream is None:
                break
            try:
                data = stream.read(3200, exception_on_overflow=False)
            except Exception as e:
                logger.warning("读取麦克风出错: %s", e)
                break
            try:
                self._recognition.send_audio_frame(data)
            except Exception as e:
                logger.warning("发送音频帧出错: %s", e)
                break

    def _close_audio(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._mic is not None:
            try:
                self._mic.terminate()
            except Exception:
                pass
            self._mic = None
