from PySide6.QtCore import QThread, Signal
from openai import OpenAI
import os
import requests
import tempfile
from concurrent.futures import ThreadPoolExecutor
from utils import get_resource, read_file

class ChatThread(QThread):
    '''对话线程，用于实现即时聊天'''
    message_received = Signal(str)          # 接收到消息信号
    chat_completed = Signal(str)            # 聊天结束信号
    audio_ready = Signal(str)               # 语音合成完成信号

    def __init__(self, message, enable_tts=True):
        super().__init__()
        self.message = message              # 用户输入的消息
        self.enable_tts = enable_tts
        self.tts_url = "http://127.0.0.1:9880/tts"
        # 只在启用TTS时创建线程池
        if self.enable_tts:
            self.tts_executor = ThreadPoolExecutor(max_workers=3)
        # 添加对话历史数组
        self.messages = []
        
    def synthesize_speech(self, text):
        """调用TTS API合成语音"""
        try:
            # 获取voice_ref.wav的绝对路径
            ref_audio_path = os.path.abspath(get_resource("resources/voice_ref.MP3"))
            
            params = {
                "text": text,
                "text_lang": "zh",
                "ref_audio_path": ref_audio_path,  # 使用绝对路径
                "prompt_lang": "zh",
                "text_split_method": "cut5",
                "streaming_mode": False,
                "batch_size": 1,
                "speed_factor": 1.0
            }
            
            # 打印请求参数用于调试
            print(f"TTS Request params: {params}")
            
            response = requests.get(self.tts_url, params=params)
            
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_file.write(response.content)
                    return temp_file.name
            else:
                # 打印详细的错误信息
                print(f"TTS请求失败: {response.status_code}")
                print(f"错误详情: {response.text}")
                return None
                    
        except Exception as e:
            print(f"语音合成错误: {str(e)}")
            return None

    def handle_tts_result(self, future):
        """处理异步语音合成的结果"""
        try:
            audio_path = future.result()
            if audio_path:
                self.audio_ready.emit(audio_path)
        except Exception as e:
            print(f"处理TTS结果时出错: {str(e)}")

    def run(self):
        prompt = read_file(r"resources\prompt.txt")
        client = OpenAI(
            api_key="sk-f3c14e0485944adbbeb9b6fc26d930f7",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        # 初始化系统提示
        if not self.messages:
            self.messages.append({'role': 'system', 'content': prompt})
            
        # 添加用户新消息
        self.messages.append({'role': 'user', 'content': self.message})

        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=self.messages,  # 使用完整的对话历史
            stream=True
        )

        full_content = ""
        current_sentence = ""
        
        for chunk in completion:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                current_sentence += content
                
                if self.enable_tts and any(punct in content for punct in ['。', '！', '？', '.', '!', '?']):
                    sentence_to_synthesize = current_sentence
                    future = self.tts_executor.submit(self.synthesize_speech, sentence_to_synthesize)
                    future.add_done_callback(self.handle_tts_result)
                    current_sentence = ""
                
                self.message_received.emit(content)
        
        # 将助手的回复添加到对话历史
        self.messages.append({'role': 'assistant', 'content': full_content})

    def __del__(self):
        """清理线程池资源"""
        if hasattr(self, 'tts_executor'):
            self.tts_executor.shutdown(wait=False)
