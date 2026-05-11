"""运行期日志与第三方库噪音控制。"""

from __future__ import annotations

import logging
import os
import warnings
from importlib import import_module


def configure_quiet_dependencies() -> None:
    """压掉已知的第三方库噪音，不影响应用自身错误。"""
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY", "False")

    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change.*",
        category=Warning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change.*",
        category=PendingDeprecationWarning,
    )
    try:
        from langchain_core._api.deprecation import (
            LangChainDeprecationWarning,
            LangChainPendingDeprecationWarning,
        )

        warnings.simplefilter("ignore", LangChainDeprecationWarning)
        warnings.simplefilter("ignore", LangChainPendingDeprecationWarning)
    except Exception:
        pass

    for name in (
        "httpx",
        "httpcore",
        "posthog",
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",
    ):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False


def configure_app_logging(level: int = logging.WARNING) -> None:
    """配置入口脚本的日志级别。"""
    configure_quiet_dependencies()
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )


def patch_langchain_reviver_default() -> None:
    """让 LangGraph 导入 JsonPlusSerializer 时不触发 allowed_objects warning。"""
    try:
        lc_load = import_module("langchain_core.load.load")
    except Exception:
        return

    original = lc_load.Reviver
    if getattr(original, "_digital_ldy_patched", False):
        return

    class QuietReviver(original):  # type: ignore[misc, valid-type]
        _digital_ldy_patched = True

        def __init__(self, *args, **kwargs) -> None:
            kwargs.setdefault("allowed_objects", "core")
            super().__init__(*args, **kwargs)

    QuietReviver.__name__ = original.__name__
    QuietReviver.__qualname__ = original.__qualname__
    QuietReviver.__module__ = original.__module__
    lc_load.Reviver = QuietReviver
