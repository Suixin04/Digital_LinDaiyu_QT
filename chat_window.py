from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                               QTextEdit, QPushButton, QHBoxLayout, QMessageBox)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeyEvent, QTextCursor, QPalette, QBrush, QImage, QPainter, QColor
from chat_thread import ChatThread, get_resource
import os
import logging
import traceback
import tempfile
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import requests


# 设置日志
logger = logging.getLogger(__name__)

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数字林黛玉")
        self.setMinimumSize(800, 600)
        self.waiting_dots = 0
        self.is_waiting = False
        self.temp_audio_files = []  # 存储临时音频文件
        
        # 设置背景图片
        self.set_background()
        
        # 创建中心部件和布局
        central_widget = QWidget()
        central_widget.setObjectName("central_widget")
        # 设置中心部件透明
        central_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 创建聊天显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setObjectName("chat_display")
        layout.addWidget(self.chat_display)

        # 创建播放器实例，只创建一次
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        
        # 创建输入区域
        input_layout = QHBoxLayout()
        self.message_input = QTextEdit()
        self.message_input.setMaximumHeight(100)
        self.message_input.setObjectName("message_input")
        self.message_input.installEventFilter(self)
        
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("send_button")
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        layout.addLayout(input_layout)
        
        # 创建等待动画计时器
        self.waiting_timer = QTimer()
        self.waiting_timer.timeout.connect(self.update_waiting_animation)
        
        # 设置样式
        self.setStyleSheet("""
            QWidget#central_widget {
                background-color: transparent;
            }
            QTextEdit {
                background-color: rgba(255, 255, 255, 0.85);
                border: 1px solid rgba(204, 204, 204, 0.8);
                border-radius: 10px;
                padding: 10px;
                color: #333333;
                font-size: 14px;
            }
            QTextEdit#chat_display {
                line-height: 1.8;
                border: 2px solid rgba(224, 224, 224, 0.8);
                border-radius: 12px;
            }
            QTextEdit#message_input {
                background-color: rgba(255, 255, 255, 0.9);
                border: 2px solid rgba(224, 224, 224, 0.8);
                border-radius: 10px;
                padding: 8px;
            }
            QTextEdit#message_input:focus {
                border: 2px solid rgba(76, 175, 80, 0.8);
            }
            QPushButton#send_button {
                background-color: rgba(76, 175, 80, 0.9);
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
                min-width: 80px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#send_button:hover {
                background-color: rgba(69, 160, 73, 0.9);
            }
            QPushButton#send_button:pressed {
                background-color: rgba(61, 139, 64, 0.9);
            }
        """)

    def set_background(self):
        try:
            # 设置背景图片
            background_path = get_resource(r"resources\background.jpg")
            logger.debug(f"尝试加载背景图片: {background_path}")
            
            if not os.path.exists(background_path):
                logger.error(f"背景图片不存在: {background_path}")
                raise FileNotFoundError(f"找不到背景图片: {background_path}")
            
            background = QImage(background_path)
            if background.isNull():
                logger.error("背景图片加载失败")
                raise Exception("背景图片加载失败")
            
            window_ratio = self.width() / self.height()
            image_ratio = background.width() / background.height()
            
            if window_ratio > image_ratio:
                scaled_width = self.width()
                scaled_height = int(scaled_width / image_ratio)
            else:
                scaled_height = self.height()
                scaled_width = int(scaled_height * image_ratio)
            
            scaled_background = background.scaled(
                scaled_width, scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            final_image = QImage(self.width(), self.height(), QImage.Format.Format_RGB32)
            if final_image.isNull():
                logger.error("无法创建最终图像")
                raise Exception("无法创建最终图像")
            
            x = (self.width() - scaled_width) // 2
            y = (self.height() - scaled_height) // 2
            
            painter = QPainter(final_image)
            painter.fillRect(0, 0, self.width(), self.height(), QColor('#f0f0f0'))
            painter.drawImage(x, y, scaled_background)
            painter.end()
            
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(final_image))
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
        self.waiting_dots = 0  # 重置等待动画的点数
        self.waiting_timer.start(500)
        
        # 创建并启动聊天线程
        self.chat_thread = ChatThread(message)
        self.chat_thread.message_received.connect(self.update_chat)
        self.chat_thread.chat_completed.connect(self.chat_completed)
        self.chat_thread.start()
    
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