"""UI 设计令牌（颜色 / 字体 / 间距 / QSS）。

参考 Figma 设计稿《数字林黛玉 UI》。
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtGui import QFont, QFontDatabase

# ---------- 色板 ---------- #

# 背景与文字
COLOR_BG = "#f7f6f3"          # 宣纸白
COLOR_FG = "#3a3838"          # 深墨
COLOR_FG_SOFT = "#6a6765"     # 次级文字
COLOR_FG_MUTED = "#8a8785"    # 极弱文字

# 气泡
COLOR_DAIYU_BG = "#f0ede8"
COLOR_DAIYU_FG = "#4a4745"
COLOR_USER_BG = "#e8d5d3"
COLOR_USER_FG = "#5a3f3d"

# 强调
COLOR_CYAN = "#7a9ea5"        # 黛青
COLOR_CYAN_LIGHT = "#b8cfd4"  # 浅黛青
COLOR_BAMBOO = "#8fa08f"      # 竹青（在线）
COLOR_ROUGE = "#c17874"       # 胭脂（录音 / 错误）
COLOR_ROUGE_LIGHT = "#e5b9b6"

# 玻璃 / 暗
COLOR_GLASS_BG = "rgba(247, 246, 243, 0.85)"
COLOR_GLASS_BORDER = "rgba(122, 158, 165, 0.18)"
COLOR_DEBUG_BG = "rgba(58, 56, 56, 0.94)"
COLOR_DEBUG_LINE = "rgba(255, 255, 255, 0.10)"


# ---------- 字体注册 ---------- #

_FONT_FAMILY: Optional[str] = None


def register_fonts() -> str:
    """注册项目内置字体，返回默认字体族名。"""
    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY

    fallback = "Microsoft YaHei"
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(here, "resources", "fonts", "LXGWWenKaiLite-Regular.ttf"),
    ]
    loaded_family: Optional[str] = None
    for path in candidates:
        if not os.path.exists(path):
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            loaded_family = families[0]
            break

    _FONT_FAMILY = loaded_family or fallback
    return _FONT_FAMILY


def app_font(size: int = 15, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = register_fonts()
    f = QFont(family, size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


# ---------- 全局 QSS ---------- #

def build_stylesheet() -> str:
    family = register_fonts()
    return f"""
    /* ====== 全局 ====== */
    * {{
        font-family: "{family}", "Microsoft YaHei", "Songti SC", serif;
        color: {COLOR_FG};
    }}
    QMainWindow, QWidget#root {{
        background-color: {COLOR_BG};
    }}

    /* ====== 顶栏 ====== */
    QFrame#header {{
        background-color: {COLOR_GLASS_BG};
        border: none;
        border-bottom: 1px solid {COLOR_GLASS_BORDER};
    }}
    QLabel#appTitle {{
        color: {COLOR_FG};
        font-size: 18px;
        letter-spacing: 2px;
    }}
    QLabel#appSubtitle {{
        color: {COLOR_FG_MUTED};
        font-size: 12px;
        letter-spacing: 1px;
    }}
    QLabel#statusText {{
        color: {COLOR_FG_SOFT};
        font-size: 12px;
    }}

    QToolButton[class="iconBtn"] {{
        background-color: transparent;
        border: none;
        border-radius: 8px;
        padding: 6px;
        color: {COLOR_FG_SOFT};
    }}
    QToolButton[class="iconBtn"]:hover {{
        background-color: rgba(184, 207, 212, 0.35);
        color: {COLOR_CYAN};
    }}
    QToolButton[class="iconBtn"]:checked {{
        background-color: rgba(184, 207, 212, 0.55);
        color: {COLOR_CYAN};
    }}

    /* ====== 滚动区域 ====== */
    QScrollArea#chatScroll, QScrollArea#chatScroll > QWidget {{
        background: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 6px 2px 6px 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(122, 158, 165, 0.30);
        border-radius: 4px;
        min-height: 36px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(122, 158, 165, 0.55);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    /* ====== 头像 ====== */
    QLabel[class="avatar"] {{
        background-color: {COLOR_CYAN_LIGHT};
        color: {COLOR_DAIYU_FG};
        font-size: 13px;
        border-radius: 16px;
    }}
    QLabel[class="avatarUser"] {{
        background-color: {COLOR_USER_BG};
        color: {COLOR_USER_FG};
        font-size: 13px;
        border-radius: 16px;
    }}
    QLabel[class="roleName"] {{
        color: {COLOR_FG_MUTED};
        font-size: 11px;
        letter-spacing: 1px;
    }}
    QLabel[class="timestamp"] {{
        color: {COLOR_FG_MUTED};
        font-size: 10px;
    }}

    /* ====== 气泡 ====== */
    QFrame#bubble_daiyu {{
        background-color: {COLOR_DAIYU_BG};
        border-radius: 16px;
    }}
    QFrame#bubble_user {{
        background-color: {COLOR_USER_BG};
        border-radius: 16px;
    }}
    QLabel[class="bubbleText_daiyu"] {{
        color: {COLOR_DAIYU_FG};
        font-size: 15px;
        background: transparent;
    }}
    QLabel[class="bubbleText_user"] {{
        color: {COLOR_USER_FG};
        font-size: 15px;
        background: transparent;
    }}

    /* ====== 输入区 ====== */
    QFrame#composer {{
        background-color: {COLOR_GLASS_BG};
        border: none;
        border-top: 1px solid {COLOR_GLASS_BORDER};
    }}
    QTextEdit#messageInput {{
        background-color: rgba(240, 237, 232, 0.6);
        border: 1px solid {COLOR_GLASS_BORDER};
        border-radius: 12px;
        padding: 10px 14px;
        color: {COLOR_FG};
        font-size: 15px;
        selection-background-color: {COLOR_CYAN_LIGHT};
    }}
    QTextEdit#messageInput:focus {{
        border: 1px solid {COLOR_CYAN};
        background-color: rgba(240, 237, 232, 0.85);
    }}

    QPushButton[class="composerBtn"] {{
        background-color: rgba(240, 237, 232, 0.6);
        border: 1px solid {COLOR_GLASS_BORDER};
        border-radius: 12px;
        color: {COLOR_FG};
        font-size: 16px;
        min-width: 48px;
        min-height: 48px;
    }}
    QPushButton[class="composerBtn"]:hover {{
        background-color: {COLOR_CYAN_LIGHT};
        color: {COLOR_FG};
    }}
    QPushButton[class="composerBtn"][recording="true"] {{
        background-color: {COLOR_ROUGE};
        border-color: {COLOR_ROUGE};
        color: white;
    }}

    QPushButton#sendBtn {{
        background-color: {COLOR_CYAN};
        border: none;
        border-radius: 12px;
        color: white;
        font-size: 15px;
        letter-spacing: 2px;
        min-width: 78px;
        min-height: 48px;
    }}
    QPushButton#sendBtn:hover {{
        background-color: #6b8e94;
    }}
    QPushButton#sendBtn:pressed {{
        background-color: #5f8086;
    }}
    QPushButton#sendBtn:disabled {{
        background-color: rgba(122, 158, 165, 0.35);
        color: rgba(255, 255, 255, 0.7);
    }}

    /* ====== 调试面板 ====== */
    QFrame#debugPanel {{
        background-color: {COLOR_DEBUG_BG};
        border: none;
        border-left: 1px solid {COLOR_GLASS_BORDER};
    }}
    QLabel#debugTitle {{
        color: rgba(229, 227, 222, 0.92);
        font-size: 13px;
        letter-spacing: 2px;
    }}
    QToolButton#debugClose {{
        background: transparent;
        border: none;
        color: rgba(229, 227, 222, 0.7);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 14px;
    }}
    QToolButton#debugClose:hover {{
        background: rgba(255, 255, 255, 0.10);
        color: white;
    }}
    QTextEdit#debugLog {{
        background: transparent;
        border: none;
        color: rgba(220, 220, 230, 0.88);
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: 12px;
        selection-background-color: rgba(122, 158, 165, 0.45);
    }}

    /* ====== 欢迎屏 ====== */
    QLabel#welcomeBadge {{
        background-color: {COLOR_CYAN_LIGHT};
        color: {COLOR_DAIYU_FG};
        font-size: 30px;
        border-radius: 40px;
    }}
    QLabel#welcomeTitle {{
        color: {COLOR_FG};
        font-size: 22px;
        letter-spacing: 4px;
    }}
    QLabel#welcomeSubtitle {{
        color: {COLOR_FG_SOFT};
        font-size: 14px;
    }}
    QLabel#welcomeHint {{
        color: {COLOR_FG_MUTED};
        font-size: 12px;
    }}
    """
