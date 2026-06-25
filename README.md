# 数字林黛玉

基于大语言模型 + 检索增强的「数字角色」网页应用，
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
- **DashScope Paraformer 实时 ASR**：桌面入口可接入实时语音识别。
- **前后端分离 Web UI**：FastAPI 后端 API + Node/Vite 前端；前端可按需请求 TTS 音频播放。

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
  api.py                 # FastAPI 后端 API
  web.py                 # 兼容旧导入的 API 转发入口
  asr.py                 # DashScope 实时 ASR 会话
  tts/                   # TTS 抽象 + 多后端
    base.py              # TTSClient ABC
    gpt_sovits.py        # 本地 GPT-SoVITS 客户端 + 启动器
    cosyvoice.py         # DashScope CosyVoice 客户端
    factory.py           # get_tts_client()
ui/                       # 可选 Qt 层
  worker.py              # QThread 包装 ChatEngine
  main_window.py         # 主窗口
frontend/                 # Node/Vite 前端
  src/                    # 浏览器 UI 与 API 调用
  package.json            # npm 脚本与前端依赖
scripts/
  test_chat.py           # CLI 烟测（无 Qt）
  load_kb.py             # 知识库加载 CLI
main.py                   # 后端 API 入口（默认自动打开浏览器）
server.py                 # 后端 API 部署入口（不自动打开浏览器）
desktop.py                # 可选 Qt 桌面入口
resources/                # prompt.txt / background.jpg / 参考音频 等
knowledge/                # 原始知识文本（txt/pdf/md）
knowledge_base/           # Chroma 持久化目录（不应提交）
GPT-SoVITS/               # GPT-SoVITS 子模块（上游：RVC-Boss/GPT-SoVITS）
```

## 快速开始

### 1. 创建环境

```bash
uv sync                              # 后端基础依赖（不含 Qt / fastembed）
uv sync --extra local-embeddings     # 推荐：加上本地嵌入后端
cd frontend && npm install           # 前端依赖
```

项目通过 `.python-version` 固定 Python 版本，`uv sync` 会自动创建或复用
本地虚拟环境；不要手动提交 `.venv/`。如果本地环境混乱，直接执行
`rm -rf .venv && uv sync --extra local-embeddings` 重建。

可选附加项：
- `--extra asr` 安装 `pyaudio`（语音输入需要）
- `--extra knowledge` 安装 `pypdf`（加载 PDF 知识需要）
- `--extra desktop` 安装 PySide6（仅可选 Qt 桌面入口需要）

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

# --- 后端 API ---
DIGITAL_LDY_WEB_HOST=127.0.0.1
DIGITAL_LDY_WEB_PORT=8000

# --- Node 前端 ---
DIGITAL_LDY_FRONTEND_MODE=dev        # dev / preview / build / none
DIGITAL_LDY_FRONTEND_HOST=127.0.0.1
DIGITAL_LDY_FRONTEND_PORT=5173
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

# 前后端一起启动
bash scripts/start_web.sh
```

常用本地启动配置：

```bash
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export TTS_BACKEND=none
export DIGITAL_LDY_ENABLE_RETRIEVAL=1
export EMBEDDING_BACKEND=fastembed
export DIGITAL_LDY_WEB_HOST=127.0.0.1
export DIGITAL_LDY_WEB_PORT=8000
export DIGITAL_LDY_FRONTEND_HOST=127.0.0.1
export DIGITAL_LDY_FRONTEND_PORT=5173

uv sync --extra local-embeddings
bash scripts/start_web.sh --host 127.0.0.1 --port 8000
```

如果 macOS 上需要通过本地代理访问 DeepSeek / GitHub，可在启动前加入：

```bash
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export all_proxy=socks5://127.0.0.1:7897
uv sync --extra local-embeddings
```

项目已包含 `socksio` 依赖，用于支持 `all_proxy=socks5://...`。如果已经有
旧的 `.venv/`，请重新执行 `uv sync --extra local-embeddings` 让依赖补齐。

### 5. 服务器部署 / URL 访问

服务器上建议关闭自动打开浏览器，后端和前端分端口运行。推荐使用一键脚本：

```bash
bash scripts/start_web.sh
```

脚本会在项目目录下使用 uv 管理后端环境，使用 npm 管理前端依赖，并默认关闭 TTS：

```text
.uv-cache/       # uv 缓存
.uv-python/      # uv 托管 Python
.venv/           # 项目虚拟环境
.hf-cache/       # Hugging Face / fastembed 辅助缓存
.model-cache/    # fastembed 模型缓存
.npm-cache/      # npm 缓存
frontend/node_modules/ # 前端依赖
```

常用参数：

```bash
bash scripts/start_web.sh --host 0.0.0.0 --port 8000
bash scripts/start_web.sh --frontend dev --frontend-port 5173
bash scripts/start_web.sh --frontend build
bash scripts/start_web.sh --frontend none
bash scripts/start_web.sh --rebuild-kb
bash scripts/start_web.sh --skip-kb
bash scripts/start_web.sh --tts gpt_sovits
bash scripts/start_web.sh --tts gpt_sovits --pretrained-models /path/to/pretrained_models
```

手动启动仍然可用：

```bash
# 终端 1：后端 API
uv sync --frozen --extra local-embeddings --extra knowledge
uv run python -m scripts.load_kb

export DEEPSEEK_API_KEY=sk-xxxxxxxx
export TTS_BACKEND=none
export DIGITAL_LDY_WEB_HOST=0.0.0.0
export DIGITAL_LDY_WEB_PORT=8000

uv run python server.py

# 终端 2：Node 前端
cd frontend
npm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev -- --host 0.0.0.0 --port 5173
```

启动后可访问：

```text
前端: http://服务器IP:5173/
后端健康检查: http://服务器IP:8000/health
```

若使用域名，通常由 Nginx/Caddy 将 `https://你的域名/` 反向代理到
前端静态文件，并将 `/api`、`/assets`、`/health` 反向代理到
`http://127.0.0.1:8000/`。健康检查地址为 `/health`，对话接口为
`POST /api/chat`，TTS 接口为 `POST /api/tts`。

更完整的 Ubuntu 流程见 [docs/ubuntu-deploy.md](docs/ubuntu-deploy.md)。

如果 GPT-SoVITS 预训练模型没有放在默认
`GPT-SoVITS/GPT_SoVITS/pretrained_models`，可通过
`--pretrained-models` 或 `GPT_SOVITS_PRETRAINED_MODELS_DIR` 指定外部目录；
未指定时仍使用 GPT-SoVITS 默认路径。

[预训练模型下载](https://pan.baidu.com/s/1AQi-X6UNRAMzUjFBMtnPlw?pwd=isin)

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
