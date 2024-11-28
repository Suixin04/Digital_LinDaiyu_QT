from PySide6.QtCore import QThread, Signal, QTimer
from openai import OpenAI
import os
import sys

def get_resource(relative_path):
    """通过相对路径，获取资源文件的绝对路径。这样获取路径方便程序打包"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def read_file(file_path):
    '''读取文件内容，用于林黛玉prompt的读取'''
    absolute_path = get_resource(file_path)
    with open(absolute_path, 'r', encoding='utf-8') as file:
        profile = file.read()
    return profile

class ChatThread(QThread):
    '''对话线程，用于实现即时聊天'''
    message_received = Signal(str)          # 接收到消息信号
    chat_completed = Signal(str)            # 聊天结束信号

    def __init__(self, message):
        super().__init__()
        self.message = message              # 用户输入的消息

    def run(self):
        prompt = read_file(r"resources\prompt.txt")
        client = OpenAI(
            api_key="sk-f3c14e0485944adbbeb9b6fc26d930f7",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': self.message}
            ],
            stream=True
        )

        full_content = ""
        current_sentence = ""
        
        for chunk in completion:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                current_sentence += content
                self.message_received.emit(content)
