"""数字林黛玉 Qt 主窗口（基于 Figma 设计稿）。"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from digital_lindaiyu.chat import ChatEngine
from digital_lindaiyu.tts import TTSClient

from . import theme
from .widgets import MessageBubble, StatusIndicator, TypingIndicator, WelcomeScreen
from .worker import ChatWorker

logger = logging.getLogger(__name__)


class ChatWindow(QMainWindow):
    """主窗口：顶栏 + 滚动消息流 + 输入区 + 可折叠调试面板。"""

    def __init__(
        self,
        engine: ChatEngine,
        tts_client: Optional[TTSClient] = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.tts_client = tts_client
        self.setWindowTitle("数字林黛玉")
        self.setMinimumSize(860, 620)
        self.resize(1180, 760)

        # 运行时状态
        self.chat_thread: Optional[ChatWorker] = None
        self.asr_session = None
        self.is_recording = False
        self.thread_id = "chat_session_1"
        self._active_bubble: Optional[MessageBubble] = None
        self._debug_width = 0

        # 音频
        self.media_player: Optional[QMediaPlayer] = None
        self.audio_output: Optional[QAudioOutput] = None
        self.audio_queue: list[str] = []
        self.played_files: set[str] = set()
        self.is_playing = False

        theme.register_fonts()
        self._build_ui()
        self.setStyleSheet(theme.build_stylesheet())
        self._apply_responsive_limits()

        if self.tts_client is not None:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(0.8)
            self.media_player.mediaStatusChanged.connect(self._on_media_status)
            self.media_player.errorOccurred.connect(self._on_media_error)
            self.cleanup_timer = QTimer(self)
            self.cleanup_timer.timeout.connect(self._cleanup_played)
            self.cleanup_timer.start(5000)

    # ============================== UI ============================== #

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        # 横向：主区 | 调试面板
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ----- 主区（垂直） ----- #
        main = QWidget()
        main.setObjectName("mainCol")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_header())
        main_layout.addWidget(self._build_chat_area(), 1)
        main_layout.addWidget(self._build_composer())

        outer.addWidget(main, 1)

        # ----- 调试面板 ----- #
        self.debug_panel = self._build_debug_panel()
        self.debug_panel.setFixedWidth(0)  # 折叠
        outer.addWidget(self.debug_panel)

    # ----------- header ----------- #

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(76)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 12, 24, 12)
        layout.setSpacing(16)

        # 左：标题块
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("数字林黛玉")
        title.setObjectName("appTitle")
        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        sub_row.setContentsMargins(0, 0, 0, 0)
        subtitle = QLabel("潇湘馆")
        subtitle.setObjectName("appSubtitle")
        dot = QLabel("·")
        dot.setObjectName("appSubtitle")
        self.status_indicator = StatusIndicator()
        sub_row.addWidget(subtitle)
        sub_row.addWidget(dot)
        sub_row.addWidget(self.status_indicator)
        sub_row.addStretch(1)
        title_box.addWidget(title)
        title_box.addLayout(sub_row)

        layout.addLayout(title_box)
        layout.addStretch(1)

        # 右：图标按钮组
        self.debug_button = QToolButton()
        self.debug_button.setProperty("class", "iconBtn")
        self.debug_button.setText("◐")
        self.debug_button.setToolTip("检索日志")
        self.debug_button.setCheckable(True)
        self.debug_button.setFixedSize(36, 36)
        self.debug_button.toggled.connect(self._toggle_debug)

        self.settings_button = QToolButton()
        self.settings_button.setProperty("class", "iconBtn")
        self.settings_button.setText("⚙")
        self.settings_button.setToolTip("设置")
        self.settings_button.setFixedSize(36, 36)

        layout.addWidget(self.debug_button)
        layout.addWidget(self.settings_button)
        return header

    # ----------- chat area ----------- #

    def _build_chat_area(self) -> QWidget:
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setObjectName("chatScroll")
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        # 居中限宽
        wrapper = QHBoxLayout(container)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addStretch(1)

        self.chat_inner = QWidget()
        self.chat_inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.chat_inner.setMaximumWidth(1080)
        self.chat_inner.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self.chat_layout = QVBoxLayout(self.chat_inner)
        self.chat_layout.setContentsMargins(24, 32, 24, 16)
        self.chat_layout.setSpacing(16)

        # 欢迎屏（消息为空时显示）
        self.welcome_screen = WelcomeScreen()
        self.chat_layout.addWidget(self.welcome_screen)

        # typing indicator（默认隐藏）
        self.typing_indicator = TypingIndicator()
        self.typing_indicator.hide()
        self.chat_layout.addWidget(self.typing_indicator)

        self.chat_layout.addStretch(1)

        wrapper.addWidget(self.chat_inner, 4)
        wrapper.addStretch(1)

        self.chat_scroll.setWidget(container)
        bar = self.chat_scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda _mn, mx: bar.setValue(mx))
        return self.chat_scroll

    def _scroll_to_bottom(self) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ----------- composer ----------- #

    def _build_composer(self) -> QFrame:
        composer = QFrame()
        composer.setObjectName("composer")

        outer = QHBoxLayout(composer)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        self.composer_center = QWidget()
        self.composer_center.setMaximumWidth(1080)
        self.composer_center.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.composer_layout = QHBoxLayout(self.composer_center)
        self.composer_layout.setContentsMargins(24, 16, 24, 18)
        self.composer_layout.setSpacing(12)

        self.message_input = QTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("写一句话寄给黛玉…  （Enter 发送 · Shift+Enter 换行）")
        self.message_input.setFixedHeight(52)
        self.message_input.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.message_input.textChanged.connect(self._update_input_height)
        self.message_input.installEventFilter(self)
        self.composer_layout.addWidget(self.message_input, 1)

        self.voice_button = QPushButton("🎙")
        self.voice_button.setProperty("class", "composerBtn")
        self.voice_button.setProperty("recording", "false")
        self.voice_button.setToolTip("按住说话")
        self.voice_button.setFixedSize(48, 48)
        self.voice_button.pressed.connect(self._start_voice_input)
        self.voice_button.released.connect(self._stop_voice_input)
        self.composer_layout.addWidget(self.voice_button)

        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("sendBtn")
        self.send_button.setMinimumSize(78, 48)
        self.send_button.clicked.connect(self.send_message)
        self.composer_layout.addWidget(self.send_button)

        outer.addWidget(self.composer_center, 4)
        outer.addStretch(1)
        return composer

    def _update_input_height(self) -> None:
        # 根据内容自适应 48 - 120
        doc_h = self.message_input.document().size().height()
        h = int(min(120, max(48, doc_h + 18)))
        self.message_input.setFixedHeight(h)

    # ----------- debug panel ----------- #

    def _build_debug_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("debugPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("检 索 日 志")
        title.setObjectName("debugTitle")
        close_btn = QToolButton()
        close_btn.setObjectName("debugClose")
        close_btn.setText("✕")
        close_btn.clicked.connect(lambda: self.debug_button.setChecked(False))
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(close_btn)
        layout.addLayout(head)

        self.log_display = QTextEdit()
        self.log_display.setObjectName("debugLog")
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display, 1)
        return panel

    def _toggle_debug(self, checked: bool) -> None:
        target = self._debug_target_width() if checked else 0
        anim = QPropertyAnimation(self.debug_panel, b"minimumWidth", self)
        anim.setDuration(280)
        anim.setStartValue(self.debug_panel.width())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._set_debug_width)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._debug_anim = anim

    def _debug_target_width(self) -> int:
        return max(280, min(360, int(self.width() * 0.32)))

    def _set_debug_width(self, width) -> None:
        self._debug_width = int(width)
        self.debug_panel.setFixedWidth(self._debug_width)
        self._apply_responsive_limits()

    def _apply_responsive_limits(self) -> None:
        available = max(560, self.width() - self._debug_width - 64)
        max_content = min(1080, available)
        self.chat_inner.setMaximumWidth(max_content)
        self.composer_center.setMaximumWidth(max_content)

        compact = self.width() < 980
        chat_x = 14 if compact else 24
        chat_top = 22 if compact else 32
        composer_x = 14 if compact else 24
        composer_y = 12 if compact else 16
        self.chat_layout.setContentsMargins(chat_x, chat_top, chat_x, 14)
        self.composer_layout.setContentsMargins(
            composer_x, composer_y, composer_x, composer_y
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        super().resizeEvent(event)
        if not hasattr(self, "chat_inner"):
            return
        if self.debug_button.isChecked():
            self._set_debug_width(self._debug_target_width())
        else:
            self._apply_responsive_limits()

    # ============================== 事件 ============================== #

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.message_input and event.type() == QKeyEvent.Type.KeyPress:
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() != Qt.KeyboardModifier.ShiftModifier
            ):
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    # ============================ 消息流 ============================ #

    def _ensure_welcome_hidden(self) -> None:
        if self.welcome_screen.isVisible():
            self.welcome_screen.hide()

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _insert_bubble(self, bubble: MessageBubble) -> None:
        # 插入到 typing 和最后 stretch 之前
        idx = self.chat_layout.indexOf(self.typing_indicator)
        if idx < 0:
            idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, bubble)
        bubble.play_enter_animation()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _add_user_bubble(self, text: str) -> MessageBubble:
        bubble = MessageBubble(role="user", timestamp=self._now())
        bubble.set_text(text)
        self._insert_bubble(bubble)
        return bubble

    def _add_daiyu_bubble(self) -> MessageBubble:
        bubble = MessageBubble(role="daiyu", timestamp=self._now())
        self._insert_bubble(bubble)
        return bubble

    # ============================== 对话 ============================== #

    def send_message(self) -> None:
        text = self.message_input.toPlainText().strip()
        if not text:
            return
        if self.chat_thread is not None and self.chat_thread.isRunning():
            return

        self._ensure_welcome_hidden()
        self._add_user_bubble(text)
        self._active_bubble = None
        self.typing_indicator.start()
        # 等待首个 chunk 前只显示 typing indicator，避免空气泡闪烁。
        self.chat_layout.removeWidget(self.typing_indicator)
        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1, self.typing_indicator
        )

        self.message_input.clear()
        self._update_input_height()
        self.send_button.setEnabled(False)
        self.status_indicator.set_status("thinking")

        self.chat_thread = ChatWorker(
            engine=self.engine,
            user_message=text,
            thread_id=self.thread_id,
            tts_client=self.tts_client,
        )
        self.chat_thread.message_received.connect(self._on_chunk)
        self.chat_thread.chat_completed.connect(self._on_completed)
        self.chat_thread.audio_ready.connect(self._handle_audio)
        self.chat_thread.log_signal.connect(self._display_log)
        self.chat_thread.start()
        self._display_log(f"→ {text}")

    def _on_chunk(self, piece: str) -> None:
        if self.typing_indicator.isVisible():
            self.typing_indicator.stop()
        if self._active_bubble is None:
            self._active_bubble = self._add_daiyu_bubble()
            self._active_bubble.set_streaming(True)
        self._active_bubble.append_text(piece)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _on_completed(self, _resp: str) -> None:
        final_text = _resp.strip()
        if self._active_bubble is None and final_text:
            self._active_bubble = self._add_daiyu_bubble()
            self._active_bubble.set_text(final_text)
        elif self._active_bubble is not None and final_text:
            self._active_bubble.set_text(final_text)
        if self._active_bubble is not None:
            self._finish_streaming_when_idle()
            return
        self.typing_indicator.stop()
        self.send_button.setEnabled(True)
        self.status_indicator.set_status("online")

    def _finish_streaming_when_idle(self) -> None:
        if self._active_bubble is None:
            self.typing_indicator.stop()
            self.send_button.setEnabled(True)
            self.status_indicator.set_status("online")
            return
        if self._active_bubble.has_pending_text():
            QTimer.singleShot(40, self._finish_streaming_when_idle)
            return
        self._active_bubble.set_streaming(False)
        self._active_bubble = None
        self.typing_indicator.stop()
        self.send_button.setEnabled(True)
        self.status_indicator.set_status("online")

    # ============================== 音频 ============================== #

    def _handle_audio(self, audio_path: str) -> None:
        if self.media_player is None:
            try:
                os.remove(audio_path)
            except OSError:
                pass
            return
        self.audio_queue.append(audio_path)
        if not self.is_playing:
            self.is_playing = True
            self._play_next()

    def _play_next(self) -> None:
        if not self.audio_queue:
            self.is_playing = False
            return
        path = self.audio_queue.pop(0)
        if not os.path.exists(path):
            self.is_playing = False
            return
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.media_player.play()

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            current = self.media_player.source().toLocalFile()
            if current:
                self.played_files.add(current)
            self._play_next()

    def _on_media_error(self, error, error_string) -> None:
        logger.warning("Media error: %s - %s", error, error_string)
        self._play_next()

    def _cleanup_played(self) -> None:
        if not self.played_files:
            return
        removed = set()
        for p in self.played_files:
            try:
                os.remove(p)
                removed.add(p)
            except OSError:
                pass
        self.played_files -= removed

    # ============================== ASR ============================== #

    def _start_voice_input(self) -> None:
        try:
            from digital_lindaiyu.asr import ASRSession
        except Exception as e:
            QMessageBox.warning(self, "语音输入不可用", str(e))
            return
        self.voice_button.setProperty("recording", "true")
        self.voice_button.setStyle(self.voice_button.style())
        self.is_recording = True
        try:
            self.asr_session = ASRSession(on_text=self._handle_asr_text)
            self.asr_session.start()
        except Exception as e:
            QMessageBox.warning(self, "语音输入不可用", str(e))
            self._reset_voice_button()

    def _stop_voice_input(self) -> None:
        if not self.is_recording:
            return
        self._reset_voice_button()
        if self.asr_session is not None:
            try:
                self.asr_session.stop()
            finally:
                self.asr_session = None
        text = self.message_input.toPlainText().strip()
        if text:
            self.send_message()

    def _reset_voice_button(self) -> None:
        self.voice_button.setProperty("recording", "false")
        self.voice_button.setStyle(self.voice_button.style())
        self.is_recording = False

    def _handle_asr_text(self, text: str) -> None:
        if text.strip():
            self.message_input.setText(text)

    # ============================ 调试日志 ============================ #

    def _display_log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{ts}] {message}")

    # ============================== 关闭 ============================== #

    def closeEvent(self, event):  # noqa: N802
        try:
            if self.chat_thread is not None and self.chat_thread.isRunning():
                self.chat_thread.requestInterruption()
                if not self.chat_thread.wait(2000):
                    self.chat_thread.terminate()
                    self.chat_thread.wait(1000)
            if self.asr_session is not None:
                try:
                    self.asr_session.stop()
                except Exception:
                    pass
            if self.media_player is not None:
                self.media_player.stop()
            for path in set(self.audio_queue) | self.played_files:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        finally:
            super().closeEvent(event)
