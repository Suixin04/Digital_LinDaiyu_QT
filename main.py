"""数字林黛玉应用入口。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from digital_lindaiyu.logging_config import configure_app_logging

configure_app_logging()

from digital_lindaiyu.chat import ChatEngine
from digital_lindaiyu.config import get_tts_config
from digital_lindaiyu.resources import get_resource
from digital_lindaiyu.tts import get_tts_client
from digital_lindaiyu.tts.gpt_sovits import start_tts_server
from ui.main_window import ChatWindow


def _ask_enable_tts() -> bool:
    return (
        QMessageBox.question(
            None,
            "TTS设置",
            "是否启用语音合成(TTS)功能？\n启用后可以听到林黛玉的声音。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def main() -> int:
    app = QApplication(sys.argv)

    enable_tts = _ask_enable_tts()
    tts_config = get_tts_config()
    tts_client = None
    tts_process = None
    splash = None

    if enable_tts:
        # 仅 GPT-SoVITS 后端需要本地启动子进程；CosyVoice 走云端 API
        if tts_config.backend == "gpt_sovits":
            try:
                splash_pixmap = QPixmap(get_resource("resources/splash_m.png"))
                splash = QSplashScreen(splash_pixmap)
                splash.show()
                splash.showMessage(
                    "正在启动语音合成服务...",
                    Qt.AlignBottom | Qt.AlignCenter,
                )
                app.processEvents()
                tts_process = start_tts_server()
            except Exception as e:
                if splash is not None:
                    splash.close()
                    splash = None
                QMessageBox.warning(
                    None,
                    "TTS不可用",
                    f"语音合成服务启动失败，将继续以文字对话。\n{e}",
                )
                enable_tts = False
        if enable_tts:
            try:
                tts_client = get_tts_client(tts_config)
            except Exception as e:
                QMessageBox.warning(None, "TTS不可用", str(e))
                tts_client = None

    engine = ChatEngine()
    window = ChatWindow(engine=engine, tts_client=tts_client)
    window.show()
    if splash is not None:
        splash.finish(window)

    ret = app.exec()
    if tts_process is not None:
        tts_process.terminate()
    return ret


if __name__ == "__main__":
    sys.exit(main())
