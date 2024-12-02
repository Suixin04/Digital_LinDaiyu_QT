import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtGui import QPixmap
from chat_window import ChatWindow
from utils import get_resource, start_tts_server

def main():
    try:
        app = QApplication(sys.argv)
        
        # 创建启动画面
        splash_path = get_resource("resources/splash.png")
        splash_pixmap = QPixmap(splash_path)
        splash = QSplashScreen(splash_pixmap)
        splash.show()
        app.processEvents()
        
        # 启动TTS服务器
        tts_process = start_tts_server()
            
        # 创建并显示主窗口
        window = ChatWindow()
        window.show()
        splash.finish(window)
        
        # 程序退出时关闭TTS服务器
        ret = app.exec()
        tts_process.terminate()
        return ret
        
    except Exception as e:
        QMessageBox.critical(None, "启动错误", f"程序启动失败:\n{str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())