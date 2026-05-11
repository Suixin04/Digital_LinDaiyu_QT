# 数字林黛玉

基于大语言模型 + 检索增强 + 语音合成的「数字角色」桌面客户端，
以《红楼梦》中的林黛玉为对话人物。

## 功能特性

- **DeepSeek 对话**：默认接入 DeepSeek `deepseek-v4-flash`（OpenAI 兼容接口），支持 DeepSeek 原生多轮工具调用。
- **Agentic RAG**：模型可按需调用 `search_knowledge_base` 检索 Chroma 知识库，而不是每轮固定拼接上下文；工具调用失败时自动回退普通 RAG。
- **可插拔嵌入后端**：
  - `fastembed` 本地 ONNX（默认 `BAAI/bge-small-zh-v1.5`，~90 MB，无 API key）
  - DashScope `text-embedding-v3`（需要 `DASHSCOPE_API_KEY`）
- **可插拔 TTS 后端**：
  - `gpt_sovits`（默认）：本地 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) HTTP 服务，高保真音色克隆。
  - `cosyvoice`：阿里 DashScope CosyVoice 云端，零部署，支持 zero-shot voice clone。
- **DashScope Paraformer 实时 ASR**：长按「语音输入」按钮即可说话。
- **Qt UI**：PySide6 主窗口、流式打字效果、TTS 顺序播放、调试日志面板。

## 项目结构

```
digital_lindaiyu/        # 核心逻辑（无 Qt 依赖，可单测）
  config.py              # 环境变量 → 类型化配置
  resources.py           # 资源路径与文本读取
  persona.py             # 角色提示词 + 离线兜底
  embeddings.py          # DashScope / FastEmbed 嵌入后端
  rag.py                 # 向量库工厂 + 检索辅助
  agent_tools.py         # DeepSeek 可调用的本地工具
  deepseek_agent.py      # DeepSeek 多轮工具调用循环
  knowledge.py           # knowledge/ → Chroma 加载器
  chat.py                # ChatEngine：工具调用优先，普通 RAG 兜底
  asr.py                 # DashScope 实时 ASR 会话
  tts/                   # TTS 抽象 + 多后端
    base.py              # TTSClient ABC
    gpt_sovits.py        # 本地 GPT-SoVITS 客户端 + 启动器
    cosyvoice.py         # DashScope CosyVoice 客户端
    factory.py           # get_tts_client()
ui/                       # Qt 层
  worker.py              # QThread 包装 ChatEngine
  main_window.py         # 主窗口
scripts/
  test_chat.py           # CLI 烟测（无 Qt）
  load_kb.py             # 知识库加载 CLI
main.py                   # Qt 应用入口
resources/                # prompt.txt / background.jpg / 参考音频 等
knowledge/                # 原始知识文本（txt/pdf/md）
knowledge_base/           # Chroma 持久化目录（不应提交）
GPT-SoVITS-v2-240821/     # 内置 GPT-SoVITS 项目副本（上游：RVC-Boss/GPT-SoVITS）
```

## 快速开始

### 1. 创建环境

```bash
uv venv .venv --python 3.10.13
uv sync                              # 基础依赖（不含 fastembed）
uv sync --extra local-embeddings     # 推荐：加上本地嵌入后端
```

可选附加项：
- `--extra asr` 安装 `pyaudio`（语音输入需要）
- `--extra knowledge` 安装 `pypdf`（加载 PDF 知识需要）

### 2. 配置 `.env`

复制 `.env.example` 为 `.env`，按需填入：

```dotenv
# --- 必需：LLM ---
DEEPSEEK_API_KEY=sk-xxxxxxxx
CHAT_MODEL=deepseek-v4-flash
CHAT_BASE_URL=https://api.deepseek.com/v1

# --- 可选：DeepSeek 工具调用 / 思考模式 ---
DIGITAL_LDY_ENABLE_TOOL_CALLS=1
DIGITAL_LDY_MAX_TOOL_ROUNDS=4
DEEPSEEK_THINKING=1
DEEPSEEK_REASONING_EFFORT=high
DIGITAL_LDY_STREAM_DELAY_MS=10

# --- 可选：检索 ---
DIGITAL_LDY_ENABLE_RETRIEVAL=1
EMBEDDING_BACKEND=auto                # auto / dashscope / fastembed
FASTEMBED_MODEL=BAAI/bge-small-zh-v1.5

# --- 可选：DashScope（用于云端嵌入 / ASR / CosyVoice）---
DASHSCOPE_API_KEY=

# --- 可选：TTS ---
TTS_BACKEND=gpt_sovits                # gpt_sovits / cosyvoice / none
COSYVOICE_VOICE=longxiaochun          # 仅 cosyvoice 用
```

### 3. 加载知识库

```bash
uv run python -m scripts.load_kb            # 增量
uv run python -m scripts.load_kb --rebuild  # 清空重建
```

> **注意**：切换嵌入后端后向量维度会变化，必须用 `--rebuild` 重建。

### 4. 启动

```bash
# 纯 CLI 烟测（不依赖 Qt）
uv run python -m scripts.test_chat "请介绍一下你"

# 完整 GUI
uv run python main.py
```

## 关于 2026 年的技术选型

### 对话：DeepSeek 工具调用 + 本地 RAG

- 默认开启 `DIGITAL_LDY_ENABLE_TOOL_CALLS=1`。模型会在需要原著信息、人物关系、诗词和样例语气时调用本地 `search_knowledge_base` 工具。
- `DEEPSEEK_THINKING=1` 时会向 DeepSeek 传入 thinking / reasoning effort 参数；若当前模型不接受该参数，程序会自动重试普通工具调用。
- 最终回答不会暴露 reasoning_content 或工具 JSON；工具结果只作为林黛玉的“记忆材料”融入口吻。
- 若工具调用链路出错，`ChatEngine` 会自动回退到旧的 LangGraph：固定检索 → 流式生成。

### TTS：留 GPT-SoVITS，但补一个云端选项

- **GPT-SoVITS**（默认）：开源、可本地离线、音色克隆质量高，缺点是需要本地模型权重（~5 GB）和一次性的环境配置成本。适合追求人物音色一致性的部署。
- **CosyVoice 2**（DashScope）：阿里通义实验室 2024 推出、持续迭代的产线级 TTS，支持 3-10 秒参考音 zero-shot 克隆，云端调用、零部署成本。把 `TTS_BACKEND=cosyvoice` 即可启用。
- 其他方向（OpenAI TTS、Fish Audio、MiniMax T2A、ElevenLabs）在中文古风对话场景表现不如以上两者稳定，故未集成。

### Embeddings：默认本地 BGE，云端可选

- **fastembed + `BAAI/bge-small-zh-v1.5`**（默认）：ONNX 量化模型，CPU 推理足够，约 90 MB，零费用，无 key 即可启动 RAG。
- **DashScope `text-embedding-v3`**：相比项目原先用的 `v2` 维度更高、语义更稳，需 `DASHSCOPE_API_KEY`。
- 没有 DashScope key 时配置会自动回退到 fastembed（`EMBEDDING_BACKEND=auto`）。

## 上游致谢

- GPT-SoVITS — <https://github.com/RVC-Boss/GPT-SoVITS>
- LangChain / LangGraph — <https://github.com/langchain-ai/langchain>
- Chroma — <https://github.com/chroma-core/chroma>
- fastembed — <https://github.com/qdrant/fastembed>
- DashScope (CosyVoice / Paraformer / text-embedding) — <https://help.aliyun.com/zh/dashscope/>
