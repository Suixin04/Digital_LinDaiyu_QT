import sys
import subprocess
import time
import requests
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtGui import QPixmap
from chat_window import ChatWindow, get_resource
import logging
import os

logger = logging.getLogger(__name__)

def start_tts_server():
    """启动TTS服务器"""
    try:
        # 获取GPT-SoVITS目录的绝对路径
        gpt_sovits_dir = os.path.join(os.getcwd(), "GPT-SoVITS-v2-240821")
        
        # 启动TTS服务器进程
        tts_process = subprocess.Popen(
            [sys.executable, "api_v2.py"],
            cwd=gpt_sovits_dir,  # 设置工作目录
            # stdout=subprocess.PIPE,
            # stderr=subprocess.PIPE
        )
        
        # 等待服务器启动
        max_retries = 30
        retry_interval = 1
        for i in range(max_retries):
            try:
                response = requests.get("http://127.0.0.1:9880/tts")
                if response.status_code == 400:  # API正常响应,但缺少参数
                    logger.info("TTS服务器启动成功")
                    return tts_process
            except requests.exceptions.ConnectionError:
                if i < max_retries - 1:
                    time.sleep(retry_interval)
                    continue
                else:
                    raise Exception("TTS服务器启动超时")
                
    except Exception as e:
        logger.error(f"启动TTS服务器失败: {str(e)}")
        raise

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