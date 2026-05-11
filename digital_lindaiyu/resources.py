"""资源路径与文本读取的小工具。"""

from __future__ import annotations

import os
import sys


def get_resource(relative_path: str) -> str:
    """返回资源的绝对路径，兼容 PyInstaller 单文件打包。"""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def read_text_resource(relative_path: str, encoding: str = "utf-8") -> str:
    """读取文本资源文件（如 prompt.txt）。"""
    absolute_path = get_resource(relative_path)
    with open(absolute_path, "r", encoding=encoding) as f:
        return f.read()
