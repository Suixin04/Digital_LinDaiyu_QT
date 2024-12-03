# chat_window.py

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                               QTextEdit, QPushButton, QHBoxLayout, QMessageBox, QGraphicsDropShadowEffect, QLabel)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeyEvent, QTextCursor, QPalette, QBrush, QImage, QPainter, QColor
from chat_thread import ChatThread
import os
import logging
import traceback
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from utils import get_resource
from chat_asr import ASRManager
import sys

# 设置日志
logger = logging.getLogger(__name__)

class ChatWindow(QMainWindow):
    def __init__(self, enable_tts=True):
        super().__init__()
        self.enable_tts = enable_tts
        self.setWindowTitle("数字林黛玉")
        self.setMinimumSize(800, 800)  # 增加高度以容纳图形

        # 初始化音频相关属性
        self.media_player = None
        self.audio_output = None
        self.audio_queue = []
        self.played_files = set()
        self.is_playing = False

        # 设置背景图片
        self.set_background()

        # 创建中心部件和布局
        central_widget = QWidget()
        central_widget.setObjectName("central_widget")
        # 设置中心部件透明
        central_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # 创建聊天显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setObjectName("chat_display")

        # 添加阴影效果
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(15)
        shadow_effect.setOffset(3, 3)
        shadow_effect.setColor(QColor(0, 0, 0, 100))
        self.chat_display.setGraphicsEffect(shadow_effect)

        self.main_layout.addWidget(self.chat_display)

        # 创建日志显示区域
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setObjectName("log_display")
        self.log_display.setStyleSheet("background-color: #f0f0f0;")
        self.log_display.setMaximumHeight(150)  # 设置日志区域高度
        self.log_display.hide()  # 初始隐藏
        self.main_layout.addWidget(self.log_display)

        # 创建状态图显示区域
        self.graph_label = QLabel()
        self.graph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.graph_label.setFixedHeight(200)  # 设置固定高度
        self.graph_label.hide()  # 初始隐藏
        self.main_layout.addWidget(self.graph_label)

        # 创建输入区域
        input_layout = QHBoxLayout()
        self.message_input = QTextEdit()
        self.message_input.setMaximumHeight(100)
        self.message_input.setObjectName("message_input")
        self.message_input.installEventFilter(self)

        button_layout = QVBoxLayout()
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("send_button")
        self.send_button.clicked.connect(self.send_message)

        self.voice_button = QPushButton("语音输入")
        self.voice_button.setObjectName("voice_button")
        self.voice_button.pressed.connect(self.start_voice_input)
        self.voice_button.released.connect(self.stop_and_send_voice_input)

        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.voice_button)

        # 添加显示/隐藏日志和推理图的按钮
        self.debug_button = QPushButton("显示检索过程")
        self.debug_button.setObjectName("debug_button")
        self.debug_button.clicked.connect(self.toggle_debug_window)
        button_layout.addWidget(self.debug_button)

        input_layout.addWidget(self.message_input)
        input_layout.addLayout(button_layout)
        self.main_layout.addLayout(input_layout)

        # 创建等待动画计时器
        self.waiting_timer = QTimer()
        self.waiting_timer.timeout.connect(self.update_waiting_animation)

        # 初始化语音识别
        self.asr_manager = None
        self.is_recording = False

        # 设置样式
        self.setStyleSheet(f"""
            QWidget#central_widget {{
                background-color: transparent;
            }}
            QTextEdit {{
                background-color: rgba(255, 255, 255, 0.85);
                border: 1px solid rgba(204, 204, 204, 0.8);
                border-radius: 15px;
                padding: 10px;
                color: #333333;
                font-size: 15px;
                font-family: 'Open Sans', Arial, sans-serif;
            }}
            QTextEdit#chat_display {{
                line-height: 1.8;
                border: 2px solid rgba(224, 224, 224, 0.8);
                border-radius: 15px;
            }}
            QTextEdit#message_input {{
                background-color: rgba(255, 255, 255, 0.9);
                border: 2px solid rgba(224, 224, 224, 0.8);
                border-radius: 15px;
                padding: 8px;
            }}
            QTextEdit#message_input:focus {{
                border: 2px solid #9D1420;
            }}
            QPushButton#send_button {{
                background-color: #9D1420;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 10px 20px;
                min-width: 80px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton#send_button:hover {{
                background-color: #B71B25;
            }}
            QPushButton#send_button:pressed {{
                background-color: #7E101A;
            }}
            QPushButton#voice_button {{
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 10px 20px;
                min-width: 80px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton#voice_button:hover {{
                background-color: #45a049;
            }}
            QPushButton#voice_button:pressed {{
                background-color: #3d8b40;
            }}
            QPushButton#debug_button {{
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 10px 20px;
                min-width: 120px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton#debug_button:hover {{
                background-color: #1976D2;
            }}
            QPushButton#debug_button:pressed {{
                background-color: #1565C0;
            }}
        """)

        # 只在启用TTS时初始化音频组件
        if self.enable_tts:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(0.8)

            self.media_player.mediaStatusChanged.connect(self.handle_media_status_changed)
            self.media_player.errorOccurred.connect(self.handle_media_error)

            self.cleanup_timer = QTimer()
            self.cleanup_timer.timeout.connect(self.cleanup_played_files)
            self.cleanup_timer.start(5000)

        # 添加对话管理
        self.thread_id = "chat_session_1"  # 可以根据需要生成唯一ID

        # 注：移除了调试窗口相关的代码
        # sys.stdout = DebugStream(self.debug_window)  # 删除重定向

    def set_background(self):
        try:
            # 设置背景图片
            background_path = get_resource(r"resources\background.jpg")
            logger.debug(f"尝试加载背景图片: {background_path}")

            if not os.path.exists(background_path):
                logger.error(f"背景图片不存在: {background_path}")
                raise FileNotFoundError(f"找不到背景图片: {background_path}")

            background_image = QImage(background_path)
            if background_image.isNull():
                logger.error("背景图片加载失败")
                raise Exception("背景图片加载失败")

            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(background_image))
            self.setPalette(palette)

            logger.debug("背景设置成功")
        except Exception as e:
            logger.error(f"设置背景失败: {str(e)}\n{traceback.format_exc()}")
            # 设置一个纯色背景作为后备方案
            self.setStyleSheet("QMainWindow { background-color: #f0f0f0; }")

    def resizeEvent(self, event):
        # 窗口大小改变时重新设置背景
        super().resizeEvent(event)
        self.set_background()

    def eventFilter(self, obj, event):
        if obj is self.message_input and event.type() == QKeyEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() != Qt.KeyboardModifier.ShiftModifier:
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    def send_message(self):
        message = self.message_input.toPlainText().strip()
        if not message:
            return

        # 显示用户消息
        self.append_message("你", message)
        self.append_assistant_prompt()

        # 清空输入框
        self.message_input.clear()

        # 开始等待动画
        self.is_waiting = True
        self.waiting_dots = 0
        self.waiting_timer.start(500)

        # 创建并启动聊天线程，传入thread_id
        self.chat_thread = ChatThread(
            message=message,
            enable_tts=self.enable_tts,
            thread_id=self.thread_id
        )
        self.chat_thread.message_received.connect(self.update_chat)
        self.chat_thread.chat_completed.connect(self.chat_completed)
        self.chat_thread.audio_ready.connect(self.handle_audio)
        self.chat_thread.log_signal.connect(self.display_log)       # 连接日志信号
        self.chat_thread.graph_signal.connect(self.display_graph)   # 连接图形信号

        self.chat_thread.start()
        self.log_display.append("已启动聊天线程。")

    def append_message(self, role, message):
        self.chat_display.append(f'<div style="margin: 10px 0;"><b>{role}:</b> {message}</div>')

    def append_assistant_prompt(self):
        self.chat_display.append('<div style="margin: 10px 0;"><b>林黛玉:</b> </div>')

    def update_chat(self, content):
        # 停止等待动画
        if self.is_waiting:
            self.is_waiting = False
            self.waiting_timer.stop()
            # 删除等待动画的点
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            for _ in range(self.waiting_dots):
                cursor.deletePreviousChar()

        # 在当前行追加内容
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(content)
        self.chat_display.setTextCursor(cursor)

        # 自动滚动到底部
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    def update_waiting_animation(self):
        if not self.is_waiting:
            return

        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # 删除之前的点
        for _ in range(self.waiting_dots):
            cursor.deletePreviousChar()

        # 更新点的数量
        self.waiting_dots = (self.waiting_dots % 3) + 1

        # 添加新的点
        cursor.insertText("." * self.waiting_dots)

    def chat_completed(self, _):
        # 聊天完成后换行
        self.chat_display.append("")
        # 停止等待动画
        self.is_waiting = False
        self.waiting_timer.stop()

    def play_next_audio(self):
        """播放队列中的下一个音频"""
        if self.audio_queue:
            audio_file = self.audio_queue.pop(0)
            print(f"Playing audio file: {audio_file}")

            # 确保文件存在
            if not os.path.exists(audio_file):
                print(f"Audio file not found: {audio_file}")
                self.is_playing = False
                return

            url = QUrl.fromLocalFile(audio_file)
            self.media_player.setSource(url)
            self.media_player.play()

            print(f"Current volume: {self.audio_output.volume()}")
        else:
            self.is_playing = False

    def handle_media_status_changed(self, status):
        """处理媒体状态变化"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # 将当前播放的文件添加到已播放集合
            current_source = self.media_player.source().toLocalFile()
            if current_source:
                self.played_files.add(current_source)
            # 播放下一个
            self.play_next_audio()

    def cleanup_played_files(self):
        """清理已播放的文件"""
        if not self.played_files:
            return

        files_to_remove = set()
        for file_path in self.played_files:
            try:
                os.remove(file_path)
                files_to_remove.add(file_path)
                print(f"Successfully cleaned up file: {file_path}")
            except Exception as e:
                print(f"Failed to clean up file {file_path}: {e}")

        # 从集合中移除已成功删除的文件
        self.played_files -= files_to_remove

    def handle_audio(self, audio_path):
        """处理新的音频文件"""
        if not self.enable_tts:
            # 如果TTS未启用，直接删除音频文件
            try:
                os.remove(audio_path)
            except:
                pass
            return

        self.audio_queue.append(audio_path)
        if not self.is_playing:
            self.is_playing = True
            self.play_next_audio()

    def handle_media_error(self, error, error_string):
        """处理媒体播放错误"""
        print(f"Media Error: {error} - {error_string}")
        # 尝试播放下一个音频
        self.play_next_audio()

    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        try:
            if hasattr(self, 'media_player'):
                self.media_player.stop()

            # 清理所有临时文件
            if hasattr(self, 'audio_queue'):
                all_files = set(self.audio_queue)
                if hasattr(self, 'played_files'):
                    all_files |= self.played_files

                for file_path in all_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        print(f"Failed to clean up file {file_path} on exit: {e}")
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            super().closeEvent(event)

    def start_voice_input(self):
        """开始语音输入"""
        self.voice_button.setText("正在录音...")
        self.voice_button.setStyleSheet("""
            QPushButton#voice_button {
                background-color: #ff4444;
                color: white;
            }
        """)
        self.is_recording = True
        self.asr_manager = ASRManager()
        self.asr_manager.text_received.connect(self.handle_asr_text)
        self.asr_manager.start()

    def stop_and_send_voice_input(self):
        """停止录音并发送消息"""
        if self.is_recording:
            self.voice_button.setText("语音输入")
            self.voice_button.setStyleSheet("")
            self.is_recording = False
            if self.asr_manager:
                self.asr_manager.stop()
                self.asr_manager = None
                # 获取输入框中的文本并发送
                message = self.message_input.toPlainText().strip()
                if message:
                    self.send_message()

    def handle_asr_text(self, text):
        """处理语音识别结果"""
        if text.strip():
            # 直接设置新的文本，不保留旧内容
            self.message_input.setText(text)

    def toggle_debug_window(self):
        """显示/隐藏日志和推理图并调整布局"""
        if self.log_display.isVisible() and self.graph_label.isVisible():
            # 隐藏日志和图形
            self.log_display.hide()
            self.graph_label.hide()
            self.debug_button.setText("显示检索过程")
            # 调整窗口大小
            self.setFixedSize(800, 800)
        else:
            # 显示日志和图形
            self.log_display.show()
            self.graph_label.show()
            self.debug_button.setText("隐藏检索过程")
            # 调整窗口大小
            self.setFixedSize(800, 1000)  # 根据需要调整高度

    def display_log(self, log_message):
        """显示日志信息"""
        self.log_display.append(f"[LOG] {log_message}")

    def display_graph(self, pixmap):
        """显示状态图"""
        self.graph_label.setPixmap(pixmap.scaled(
            self.graph_label.width(),
            self.graph_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
