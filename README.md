# 数字林黛玉

## 项目背景
随着人工智能技术的快速发展，基于自然语言处理和深度学习的聊天机器人已成为研究热点。然而，大多数聊天机器人更关注功能性和实用性，忽略了文化传承和艺术表达。本项目旨在通过 AI 技术复刻中国经典文学《红楼梦》中林黛玉这一文学形象，让用户在与 AI 的互动中感受古典文化之美，同时探索 AI 在情感表达与语音合成领域的潜力。

## 功能特点

- **智能对话**: 基于大语言模型，模拟林黛玉的性格特征和语言风格进行对话
- **语音合成**: 使用 GPT-SoVITS 技术，实现富有情感的语音输出
- **优雅界面**: 采用 PySide6 构建的图形界面，搭配古典风格的背景设计
- **流式响应**: 支持对话内容的实时打字显示效果
- **语音队列**: 实现连贯的语音播放，自动清理临时音频文件

## 项目架构
```bash
digital-daiyu/

├── main.py                     # 程序入口
├── chat_window.py              # 主窗口界面
├── chat_thread.py              # 对话线程处理
├── resources/                  # 资源文件目录
│ ├── background.jpg            # 背景图片
│ ├── prompt.txt                # 角色设定文本
│ ├── splash.png                # 启动画面
│ └── voice_ref.MP3             # 语音参考音频
└── GPT-SoVITS-v2-240821/       # 语音合成模块
└── api_v2.py                   # TTS服务API
```

## 技术栈

- **前端界面**: PySide6 (Qt for Python)
- **对话模型**: Qwen-Plus (通过 DashScope API)
- **语音合成**: GPT-SoVITS
- **开发语言**: Python 3.10.13

## 安装说明

1. 克隆项目仓库

```bash
git clone https://github.com/your-username/digital-daiyu.git
cd digital-daiyu
```

2. 配置python环境

```bash
conda create -n digital-daiyu python=3.10.13
conda activate digital-daiyu
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 下载必要的模型文件
- 将语音合成模型文件放置在 `GPT-SoVITS-v2-240821/GPT_SoVITS/pretrained_models/` 目录下

4. 启动程序

```bash
python main.py
```

## 使用说明

1. 程序启动后会自动加载 TTS 服务
2. 在输入框中输入文字，按回车键或点击发送按钮进行对话
3. AI 会以林黛玉的身份回复，并通过语音播放
4. 支持连续对话，语音会自动排队播放

## 开发说明

- 主程序入口 `main.py` 负责初始化应用程序和 TTS 服务
- `chat_window.py` 包含主界面实现，处理用户交互和音频播放
- `chat_thread.py` 负责对话生成和语音合成的异步处理
- TTS 服务通过 HTTP API 提供语音合成功能

## 注意事项

- 需要确保 GPT-SoVITS 模型文件正确配置
- 首次启动时需要等待 TTS 服务初始化
- 建议使用耳机以获得更好的语音体验

## 许可证

[添加许可证信息]

## 贡献指南

[添加贡献指南]

## 致谢

- GPT-SoVITS 项目提供的语音合成技术支持
- 阿里云 DashScope 提供的大语言模型服务

