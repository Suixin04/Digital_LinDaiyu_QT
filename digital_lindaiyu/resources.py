"""资源路径与文本读取的小工具。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """返回项目根目录，兼容 PyInstaller 单文件打包。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return PROJECT_ROOT


def resolve_project_path(relative_path: str | Path) -> Path:
    """把项目内路径解析成绝对路径，并兼容 Windows 风格分隔符。"""
    path = Path(str(relative_path).replace("\\", "/"))
    if path.is_absolute():
        return path
    return get_project_root() / path


def get_resource(relative_path: str | Path) -> str:
    """返回资源的绝对路径。"""
    return str(resolve_project_path(relative_path))


def read_text_resource(relative_path: str, encoding: str = "utf-8") -> str:
    """读取文本资源文件（如 prompt.txt）。"""
    absolute_path = resolve_project_path(relative_path)
    with absolute_path.open("r", encoding=encoding) as f:
        return f.read()
