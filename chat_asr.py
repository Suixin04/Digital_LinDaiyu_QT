import pyaudio
import dashscope
from PySide6.QtCore import QThread, Signal
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

class ASRCallback(RecognitionCallback):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.mic = None
        self.stream = None

    def on_open(self) -> None:
        print('ASR开始录音')
        self.mic = pyaudio.PyAudio()
        self.stream = self.mic.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=3200
        )

    def on_close(self) -> None:
        print('ASR停止录音')
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.mic:
            self.mic.terminate()
        self.stream = None
        self.mic = None

    def on_event(self, result: RecognitionResult) -> None:
        try:
            sentence = result.get_sentence()
            if sentence and sentence.get('text'):
                self.manager.text_received.emit(sentence['text'])
        except Exception as e:
            print(f"处理语音识别结果出错: {e}")

class ASRManager(QThread):
    text_received = Signal(str)

    def __init__(self):
        super().__init__()
        dashscope.api_key = 'sk-5af05cf94fbe4be8b1c6c55bf3d0a8fe'
        self.callback = ASRCallback(self)
        self.recognition = Recognition(
            model='paraformer-realtime-v2',
            format='pcm',
            sample_rate=16000,
            callback=self.callback
        )
        self.running = False

    def run(self):
        self.running = True
        self.recognition.start()
        
        while self.running:
            if self.callback.stream:
                data = self.callback.stream.read(3200, exception_on_overflow=False)
                self.recognition.send_audio_frame(data)
            else:
                break

    def stop(self):
        self.running = False
        self.recognition.stop()