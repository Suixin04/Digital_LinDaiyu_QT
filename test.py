# 测试知识库检索
from chat_thread import ChatThread
from PySide6.QtCore import QCoreApplication
import sys

def message_received(text):
    print(text, end="")

def chat_completed(_):
    print("\n--- 回答完成 ---")
    app.quit()

app = QCoreApplication(sys.argv)

# 创建聊天线程并测试
chat = ChatThread("请介绍一下红楼梦中的林黛玉", enable_tts=False)
chat.message_received.connect(message_received)
chat.chat_completed.connect(chat_completed)
chat.start()

sys.exit(app.exec())