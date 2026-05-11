"""可复用的 Qt 视觉组件（消息气泡、状态点、打字指示器、欢迎屏）。

设计源自 Figma《数字林黛玉》设计稿。
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


# ============================ 消息气泡 ============================ #


class MessageBubble(QWidget):
    """一条消息：左/右对齐 + 头像 + 角色名 + 气泡体 + 时间戳。"""

    def __init__(
        self,
        role: str,
        timestamp: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = role  # "user" / "daiyu"
        self._streaming = False
        self._caret_visible = False
        self._text_buffer = ""
        self._last_rendered = ""

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._build(timestamp)

        # 光标
        self._caret_timer = QTimer(self)
        self._caret_timer.setInterval(550)
        self._caret_timer.timeout.connect(self._toggle_caret)

    # ---------------- 构建 ---------------- #

    def _build(self, timestamp: str) -> None:
        is_daiyu = self.role == "daiyu"

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        avatar = QLabel("黛" if is_daiyu else "我")
        avatar.setObjectName("avatar")
        avatar.setProperty("class", "avatar" if is_daiyu else "avatarUser")
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 中间列：角色名 + 气泡 + 时间戳
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)

        role_name = QLabel("林黛玉" if is_daiyu else "我")
        role_name.setProperty("class", "roleName")

        bubble_body = QFrame()
        bubble_body.setObjectName(f"bubble_{self.role}")
        body_layout = QVBoxLayout(bubble_body)
        body_layout.setContentsMargins(20, 14, 20, 14)
        body_layout.setSpacing(0)

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.text_label.setProperty(
            "class", "bubbleText_daiyu" if is_daiyu else "bubbleText_user"
        )
        body_layout.addWidget(self.text_label)

        # 阴影
        shadow = QGraphicsDropShadowEffect(bubble_body)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(58, 56, 56, 28))
        bubble_body.setGraphicsEffect(shadow)
        self._bubble_body = bubble_body
        self._bubble_shadow = shadow

        bubble_body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        bubble_body.setMaximumWidth(720)

        ts_label = QLabel(timestamp)
        ts_label.setProperty("class", "timestamp")

        if is_daiyu:
            role_name.setAlignment(Qt.AlignmentFlag.AlignLeft)
            ts_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            col.addWidget(role_name)
            col.addWidget(bubble_body, 0, Qt.AlignmentFlag.AlignLeft)
            col.addWidget(ts_label)
        else:
            role_name.setAlignment(Qt.AlignmentFlag.AlignRight)
            ts_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            col.addWidget(role_name)
            col.addWidget(bubble_body, 0, Qt.AlignmentFlag.AlignRight)
            col.addWidget(ts_label)

        if is_daiyu:
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            outer.addLayout(col)
            outer.addStretch(1)
        else:
            outer.addStretch(1)
            outer.addLayout(col)
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

    # ---------------- 文本与状态 ---------------- #

    def set_text(self, text: str) -> None:
        self._text_buffer = text
        self._render()

    def append_text(self, piece: str) -> None:
        if not piece:
            return
        self._text_buffer += piece
        self._render()

    def flush_now(self) -> None:
        self._render()

    def has_pending_text(self) -> bool:
        return False

    def set_streaming(self, on: bool) -> None:
        self._streaming = on
        if on:
            self._caret_visible = True
            self._caret_timer.start()
            # 加强阴影 + 黛青光晕
            self._bubble_shadow.setColor(QColor(122, 158, 165, 60))
            self._bubble_shadow.setBlurRadius(28)
        else:
            self._caret_timer.stop()
            self._caret_visible = False
            self._bubble_shadow.setColor(QColor(58, 56, 56, 28))
            self._bubble_shadow.setBlurRadius(20)
        self._render()

    def _toggle_caret(self) -> None:
        self._caret_visible = not self._caret_visible
        self._render()

    def _render(self) -> None:
        text = self._text_buffer
        if self._streaming:
            # 仿光标：用细窄竖线字符
            text = text + ("▎" if self._caret_visible else " ")
        if text == self._last_rendered:
            return
        self._last_rendered = text
        self.text_label.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        super().resizeEvent(event)
        available = max(320, self.width() - 64)
        self._bubble_body.setMaximumWidth(max(280, int(available * 0.68)))

    # ---------------- 入场动画 ---------------- #

    def play_enter_animation(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _cleanup() -> None:
            # 移除透明度效果，让气泡阴影/正常绘制恢复
            self.setGraphicsEffect(None)

        anim.finished.connect(_cleanup)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._enter_anim = anim


# ============================ 打字指示器 ============================ #


class TypingIndicator(QWidget):
    """三点呼吸式（带头像 + 气泡背景）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._phase = 0.0

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        avatar = QLabel("黛")
        avatar.setProperty("class", "avatar")
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col = QVBoxLayout()
        col.setSpacing(6)
        name = QLabel("林黛玉")
        name.setProperty("class", "roleName")
        col.addWidget(name)

        bubble = QFrame()
        bubble.setObjectName("bubble_daiyu")
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(0)
        self._dots = _DotsCanvas()
        bl.addWidget(self._dots)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        shadow = QGraphicsDropShadowEffect(bubble)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(122, 158, 165, 50))
        bubble.setGraphicsEffect(shadow)

        col.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(col)
        outer.addStretch(1)

    def start(self) -> None:
        self._dots.start()
        self.show()

    def stop(self) -> None:
        self._dots.stop()
        self.hide()


class _DotsCanvas(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(48, 16))
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._step)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _step(self) -> None:
        self._phase = (self._phase + 0.10) % (2 * math.pi)
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(theme.COLOR_CYAN)
        cx = 8
        cy = self.height() / 2
        for i in range(3):
            t = self._phase - i * 0.7
            wave = 0.5 + 0.5 * math.sin(t)
            r = 3.0 + 1.2 * wave
            alpha = int(80 + 175 * wave)
            c = QColor(color)
            c.setAlpha(alpha)
            painter.setBrush(c)
            y = cy - 3 * wave  # 上下浮动
            painter.drawEllipse(int(cx - r), int(y - r), int(r * 2), int(r * 2))
            cx += 14


# ============================ 状态指示点 ============================ #


class StatusIndicator(QWidget):
    """脉冲圆点 + 文字。status: online / thinking / offline。"""

    _COLORS = {
        "online": theme.COLOR_BAMBOO,
        "thinking": theme.COLOR_CYAN,
        "offline": theme.COLOR_ROUGE,
    }
    _LABELS = {"online": "在线", "thinking": "思考中", "offline": "离线"}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._status = "online"
        self._phase = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._dot = _PulseDot(QColor(self._COLORS[self._status]))
        self._label = QLabel(self._LABELS[self._status])
        self._label.setObjectName("statusText")
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

    def set_status(self, status: str) -> None:
        if status not in self._COLORS:
            return
        self._status = status
        self._dot.set_color(QColor(self._COLORS[status]))
        self._dot.set_pulsing(status != "offline")
        self._label.setText(self._LABELS[status])


class _PulseDot(QWidget):
    def __init__(self, color: QColor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = color
        self._phase = 0.0
        self._pulsing = True
        self.setFixedSize(10, 10)
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._step)
        self._timer.start()

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def set_pulsing(self, on: bool) -> None:
        self._pulsing = on
        if on and not self._timer.isActive():
            self._timer.start()
        self.update()

    def _step(self) -> None:
        if not self._pulsing:
            return
        self._phase = (self._phase + 0.06) % (2 * math.pi)
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        center = self.rect().center()
        if self._pulsing:
            scale = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(self._phase))
        else:
            scale = 0.7

        glow = QColor(self._color)
        glow.setAlpha(70)
        gr = 5 * scale + 2
        painter.setBrush(glow)
        painter.drawEllipse(center, gr, gr)

        core = QColor(self._color)
        if not self._pulsing:
            core.setAlpha(120)
        painter.setBrush(core)
        painter.drawEllipse(center, 3.5, 3.5)


# ============================ 欢迎屏 ============================ #


class WelcomeScreen(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(16)
        layout.addStretch(1)

        badge = QLabel("黛")
        badge.setObjectName("welcomeBadge")
        badge.setFixedSize(80, 80)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("数字林黛玉")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("潇湘馆中，竹影婆娑。\n以现代之技，续千古之情。")
        subtitle.setObjectName("welcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        hint = QLabel("你可以问她关于《红楼梦》的故事\n或是与她谈论诗词歌赋")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addStretch(2)
