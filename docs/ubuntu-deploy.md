# Ubuntu 部署流程

本文档面向 `feat/web-ui` 分支。当前结构为前后端分离：
FastAPI 提供后端 API，Node/Vite 提供浏览器前端。

## 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential ffmpeg
```

安装 uv，并准备 Node.js 18+ / npm：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.profile
uv --version
node --version
npm --version
```

如果服务器没有 Node，先用系统软件源、nvm 或 NodeSource 安装 Node.js 18+
及 npm，再继续后续步骤。

## 2. 拉取完整项目

```bash
git clone --branch feat/web-ui --recurse-submodules <你的仓库地址> Digital_LinDaiyu_QT
cd Digital_LinDaiyu_QT

# 如果 clone 时没有带 --recurse-submodules：
git submodule update --init --recursive
```

## 3. 配置环境变量

```bash
cp .env.server.example .env
nano .env
```

至少填写：

```dotenv
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

服务器部署建议保留这些默认值：

```dotenv
DIGITAL_LDY_WEB_HOST=0.0.0.0
DIGITAL_LDY_WEB_PORT=8000
DIGITAL_LDY_FRONTEND_MODE=dev
DIGITAL_LDY_FRONTEND_HOST=0.0.0.0
DIGITAL_LDY_FRONTEND_PORT=5173
EMBEDDING_BACKEND=fastembed
TTS_BACKEND=none
```

uv 的缓存、托管 Python 和虚拟环境会放在项目目录下：

```text
.uv-cache/
.uv-python/
.venv/
.hf-cache/
.model-cache/
.npm-cache/
```

这些目录都已加入 `.gitignore`，不用提交。

## 4. 一键启动

```bash
bash scripts/start_web.sh
```

脚本会依次完成：

```text
检查/拉取子模块
uv sync --frozen --extra local-embeddings --extra knowledge
npm install
增量加载 knowledge/ 到 knowledge_base/
启动 FastAPI 后端和 Vite 前端
```

常用参数：

```bash
# 指定端口
bash scripts/start_web.sh --host 0.0.0.0 --port 8000

# 前端模式：dev / preview / build / none
bash scripts/start_web.sh --frontend dev --frontend-port 5173
bash scripts/start_web.sh --frontend build
bash scripts/start_web.sh --frontend none

# 切换嵌入模型或知识文本后，重建知识库
bash scripts/start_web.sh --rebuild-kb

# 只启动服务，不更新知识库
bash scripts/start_web.sh --skip-kb

# 依赖已经装好时，跳过 uv sync
bash scripts/start_web.sh --no-sync

# GPT-SoVITS 预训练模型在外部目录时
bash scripts/start_web.sh --tts gpt_sovits --pretrained-models /path/to/pretrained_models
```

访问：

```text
http://服务器IP:8000/
http://服务器IP:8000/health
http://服务器IP:5173/
```

## 5. TTS 说明

Web UI 可以通过语音开关请求后端 TTS。服务器部署默认关闭 TTS：

```bash
bash scripts/start_web.sh --no-tts
```

如果要准备 GPT-SoVITS 服务，可用：

```bash
bash scripts/start_web.sh --tts gpt_sovits
```

这要求：

```text
GPT-SoVITS 子模块已拉取
GPT-SoVITS 环境已按其 install.sh/README 单独配置
林黛玉 GPT 权重和 SoVITS 权重已放到 .env 指定路径
```

默认权重路径：

```text
GPT-SoVITS/GPT_weights_v4/digital_ldy-e15.ckpt
GPT-SoVITS/SoVITS_weights_v4/digital_ldy_e4_s156_l64.pth
```

这些 v4 训练权重通过 GPT-SoVITS 子模块的 Git LFS 拉取。

预训练底模缺省路径仍是：

```text
GPT-SoVITS/GPT_SoVITS/pretrained_models
```

如果底模放在别处，传：

```bash
bash scripts/start_web.sh --tts gpt_sovits --pretrained-models /data/models/pretrained_models
```

或在 `.env` 中写：

```dotenv
GPT_SOVITS_PRETRAINED_MODELS_DIR=/data/models/pretrained_models
```

## 6. 生产反向代理

直接暴露 5173 和 8000 端口可以测试；正式使用建议把前端构建后放到
Nginx/Caddy 后面，并将 API 转发到后端。

Nginx 示例：

```nginx
server {
    listen 80;
    server_name your.domain.com;
    root /srv/Digital_LinDaiyu_QT/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /assets/ {
        try_files $uri @backend_assets;
    }

    location @backend_assets {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

## 7. 常见检查

```bash
# 健康检查
curl http://127.0.0.1:8000/health

# TTS 状态
curl http://127.0.0.1:8000/api/tts/status

# 手动加载知识库
uv run python -m scripts.load_kb --rebuild

# 文字接口测试
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"请介绍一下你","speak":false}'
```

如果首次运行 fastembed，本地 BGE 模型会下载到缓存目录；没有外网时可提前把
`.uv-cache/` 和 fastembed 模型缓存准备好，或改用 DashScope 嵌入。
