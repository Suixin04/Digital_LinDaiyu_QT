import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from chat_window import ChatWindow
from utils import get_resource, start_tts_server

def main():
    try:
        app = QApplication(sys.argv)
        
        # 询问用户是否启用TTS
        enable_tts = QMessageBox.question(
            None, 
            "TTS设置",
            "是否启用语音合成(TTS)功能？\n启用后可以听到林黛玉的声音。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes
        
        splash = None
        tts_process = None
        
        if enable_tts:
            # 创建启动画面
            splash_path = get_resource("resources/splash_m.png")
            splash_pixmap = QPixmap(splash_path)
            splash = QSplashScreen(splash_pixmap)
            splash.show()
            splash.showMessage("正在启动语音合成服务...", Qt.AlignBottom | Qt.AlignCenter)
            app.processEvents()
            
            # 启动TTS服务器
            tts_process = start_tts_server()
            
        # 创建并显示主窗口
        window = ChatWindow(enable_tts=enable_tts)
        window.show()
        
        if splash:
            splash.finish(window)
        
        # 程序退出时关闭TTS服务器
        ret = app.exec()
        if tts_process:
            tts_process.terminate()
        return ret
        
    except Exception as e:
        QMessageBox.critical(None, "启动错误", f"程序启动失败:\n{str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())