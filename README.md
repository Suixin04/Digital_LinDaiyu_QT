# 数字林黛玉

## 项目背景
随着人工智能技术的快速发展，基于自然语言处理和深度学习的聊天机器人已成为研究热点。然而，大多数聊天机器人更关注功能性和实用性，忽略了文化传承和艺术表达。本项目旨在通过 AI 技术复刻中国经典文学《红楼梦》中林黛玉这一文学形象，让用户在与 AI 的互动中感受古典文化之美，同时探索 AI 在情感表达与语音合成领域的潜力。

## 功能特点

- **智能对话**: 基于大语言模型，模拟林黛玉的性格特征和语言风格进行对话
- **知识检索**: 使用向量数据库存储和检索相关知识，确保回答的准确性和连贯性
- **语音合成**: 使用 GPT-SoVITS 技术，实现富有情感的语音输出
- **优雅界面**: 采用 PySide6 构建的图形界面，搭配古典风格的背景设计
- **流式响应**: 支持对话内容的实时打字显示效果
- **语音队列**: 实现连贯的语音播放，自动清理临时音频文件
- **多轮对话**: 支持上下文记忆，实现连贯的对话体验
- **检索可视化**: 提供知识检索过程的可视化展示

## 项目架构
```bash
digital-daiyu/
├── main.py                     # 程序入口
├── chat_window.py              # 主窗口界面
├── chat_thread.py              # 对话线程处理
├── load_knowledge.py           # 知识库加载模块
├── tongyi_embeddings.py        # 通义千问 Embeddings 实现
├── resources/                  # 资源文件目录
│ ├── background.jpg           # 背景图片
│ ├── prompt.txt              # 角色设定文本
│ ├── splash.png              # 启动画面
│ └── voice_ref.MP3           # 语音参考音频
├── knowledge/                  # 知识库目录
│ ├── txt/                    # 文本知识
│ │ ├── 人物介绍/            # 人物相关知识
│ │ └── ...                  # 其他知识分类
│ ├── pdf/                    # PDF文档知识
│ └── md/                     # Markdown知识
└── GPT-SoVITS-v2-240821/      # 语音合成模块
```

## 技术栈

- **前端界面**: PySide6 (Qt for Python)
- **对话模型**: Qwen-Plus (通过 DashScope API)
- **向量数据库**: Chroma DB
- **文本嵌入**: 通义千问 Embedding
- **语音合成**: GPT-SoVITS
- **语音识别**: DashScope ASR
- **开发语言**: Python 3.10.13

## 安装说明

### 使用yml文件一步安装
```bash
conda env create -f Digital_LDY_environment.yml
```

1. 克隆项目仓库
```bash
git clone https://github.com/your-username/digital-daiyu.git
cd digital-daiyu
```

2. 配置python环境
```bash
conda create -n YOURNAME python=3.10.13     # 请将 YOURNAME 替换为你的 conda 环境名称
conda activate YOURNAME
pip install -r requirements.txt
pip uninstall torch-lightning -y
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install torch-lightning
pip install dashscope
pip install pyaudio
```

3. 下载必要的模型文件
[林黛玉语音预训练模型](https://pan.baidu.com/s/1AQi-X6UNRAMzUjFBMtnPlw?pwd=isin)
- 将语音合成模型文件放置在 `GPT-SoVITS-v2-240821/GPT_SoVITS/pretrained_models/` 目录下

4. 准备知识库
```bash
python load_knowledge.py  # 加载知识库文件到向量数据库
```

5. 启动程序
```bash
python main.py
```

## 使用说明

1. 程序启动后会自动加载 TTS 服务和知识库
2. 在输入框中输入文字，按回车键或点击发送按钮进行对话
3. AI 会以林黛玉的身份回复，并通过语音播放
4. 支持连续对话，语音会自动排队播放
5. 可以点击"显示检索过程"查看知识库检索的详细信息
6. 支持语音输入功能，长按"语音输入"按钮进行录音

## 知识库说明

项目使用 Chroma 向量数据库存储以下知识：
- 林黛玉的性格特征和语言风格
- 与其他人物的关系网络
- 典型的对话场景和回答模板
- 《红楼梦》相关的背景知识

知识库支持：
- 多种格式：支持 TXT、PDF、Markdown 等格式
- 自动分割：根据语义自动分割长文本
- 相似度检索：使用余弦相似度进行相关内容检索
- 动态更新：支持在对话过程中动态扩充知识

## 注意事项

- 需要确保 GPT-SoVITS 模型文件正确配置
- 首次启动时需要等待 TTS 服务初始化
- 建议使用耳机以获得更好的语音体验
- 知识库加载可能需要一定时间
- 请确保 API Key 正确配置

## 许可证

[添加许可证信息]

## 贡献指南

[添加贡献指南]

## 致谢

- GPT-SoVITS 项目提供的语音合成技术支持：https://github.com/RVC-Boss/GPT-SoVITS
- 阿里云 DashScope 提供的大语言模型服务：https://www.aliyun.com/product/bailian
- LangChain 提供的框架支持：https://github.com/langchain-ai/langchain
- Chroma DB 提供的向量数据库支持：https://github.com/chroma-core/chroma

