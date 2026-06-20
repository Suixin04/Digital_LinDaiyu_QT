"""Web service entrypoint for server deployment."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from collections import deque
from typing import Deque

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chat import ChatEngine
from .config import env_flag, get_chat_model_config
from .logging_config import configure_app_logging
from .resources import resolve_project_path

configure_app_logging()

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    thread_id: str


class HealthResponse(BaseModel):
    status: str
    model: str
    llm_configured: bool
    retrieval_enabled: bool


class ChatService:
    """Owns the shared ChatEngine used by HTTP requests.

    ChatEngine stores per-request callbacks on the instance, so access is
    serialized to avoid interleaving concurrent requests.
    """

    def __init__(self) -> None:
        self._engine: ChatEngine | None = None
        self._lock = threading.RLock()
        self._logs: Deque[str] = deque(maxlen=200)

    def _log(self, message: str) -> None:
        self._logs.append(message)
        logger.info(message)

    def _get_engine(self) -> ChatEngine:
        if self._engine is None:
            self._engine = ChatEngine(log=self._log)
        return self._engine

    def reply(self, message: str, thread_id: str) -> str:
        with self._lock:
            return self._get_engine().stream(message, thread_id=thread_id)


chat_service = ChatService()
app = FastAPI(title="Digital Lin Daiyu", version="0.1.0")

resources_dir = resolve_project_path("resources")
if resources_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(resources_dir)), name="assets")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    icon_path = resolve_project_path("resources/icon.ico")
    if not icon_path.exists():
        raise HTTPException(status_code=404, detail="favicon not found")
    return FileResponse(icon_path)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    config = get_chat_model_config()
    return HealthResponse(
        status="ok",
        model=config.model,
        llm_configured=config.is_available,
        retrieval_enabled=env_flag("DIGITAL_LDY_ENABLE_RETRIEVAL", True),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    thread_id = _normalize_thread_id(request.thread_id)
    reply = await run_in_threadpool(chat_service.reply, message, thread_id)
    return ChatResponse(reply=reply, thread_id=thread_id)


def _normalize_thread_id(thread_id: str | None) -> str:
    cleaned = (thread_id or "").strip()
    if not cleaned:
        return f"web-{uuid.uuid4().hex}"
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:."
    )
    normalized = "".join(ch for ch in cleaned if ch in allowed)[:128]
    return normalized or f"web-{uuid.uuid4().hex}"


def run() -> None:
    import uvicorn

    host = os.getenv("DIGITAL_LDY_WEB_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORT") or os.getenv("DIGITAL_LDY_WEB_PORT") or "8000")
    except ValueError:
        port = 8000
    uvicorn.run("digital_lindaiyu.web:app", host=host, port=port)


_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>数字林黛玉</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #241914;
      --muted: #6f625d;
      --paper: rgba(255, 252, 246, 0.94);
      --paper-strong: #fffaf1;
      --line: rgba(65, 48, 38, 0.16);
      --accent: #8b2e3d;
      --accent-dark: #5e1e2a;
      --green: #466a4d;
      --shadow: 0 22px 80px rgba(24, 16, 12, 0.22);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(250, 246, 237, 0.92), rgba(250, 246, 237, 0.7)),
        url("/assets/background.jpg") center / cover fixed;
    }

    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
      width: min(1120px, 100%);
      margin: 0 auto;
      padding: 20px;
      gap: 14px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 62px;
      padding: 0 4px;
    }

    h1 {
      margin: 0;
      font-size: 30px;
      line-height: 1.15;
      font-weight: 650;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--green);
      font-size: 14px;
      white-space: nowrap;
    }

    .status::before {
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--green);
      box-shadow: 0 0 0 4px rgba(70, 106, 77, 0.16);
    }

    main {
      min-height: 0;
      display: grid;
      grid-template-rows: 1fr;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .messages {
      min-height: 0;
      overflow-y: auto;
      padding: 26px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .bubble {
      max-width: min(720px, 88%);
      padding: 13px 15px;
      border: 1px solid var(--line);
      border-radius: 8px;
      white-space: pre-wrap;
      line-height: 1.65;
      word-break: break-word;
      overflow-wrap: anywhere;
      font-size: 16px;
    }

    .bubble.assistant {
      align-self: flex-start;
      background: var(--paper-strong);
    }

    .bubble.user {
      align-self: flex-end;
      color: #fff;
      background: linear-gradient(135deg, var(--accent), var(--accent-dark));
      border-color: transparent;
    }

    .composer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      padding: 0 4px;
    }

    textarea {
      width: 100%;
      min-height: 54px;
      max-height: 180px;
      resize: vertical;
      border: 1px solid rgba(65, 48, 38, 0.22);
      border-radius: 8px;
      background: rgba(255, 252, 246, 0.96);
      color: var(--ink);
      padding: 14px 15px;
      font: inherit;
      line-height: 1.5;
      outline: none;
      box-shadow: 0 12px 34px rgba(24, 16, 12, 0.12);
    }

    textarea:focus {
      border-color: rgba(139, 46, 61, 0.5);
    }

    button {
      width: 86px;
      height: 54px;
      border: 0;
      border-radius: 8px;
      color: #fff;
      background: var(--accent);
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      box-shadow: 0 12px 34px rgba(94, 30, 42, 0.22);
    }

    button:disabled {
      cursor: progress;
      opacity: 0.64;
    }

    .error {
      color: #8b2e3d;
    }

    @media (max-width: 720px) {
      .app {
        padding: 12px;
        gap: 10px;
      }

      h1 {
        font-size: 24px;
      }

      .messages {
        padding: 16px;
      }

      .bubble {
        max-width: 96%;
        font-size: 15px;
      }

      .composer {
        grid-template-columns: 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <h1>数字林黛玉</h1>
      <div class="status" id="status">在线</div>
    </header>
    <main>
      <div class="messages" id="messages" aria-live="polite">
        <div class="bubble assistant">风露清愁，已在潇湘馆候着。你来了，便说说今日心事罢。</div>
      </div>
    </main>
    <form class="composer" id="form">
      <textarea id="message" name="message" rows="2" maxlength="4000" placeholder="写一句话寄给黛玉..."></textarea>
      <button id="send" type="submit">发送</button>
    </form>
  </div>
  <script>
    const form = document.getElementById("form");
    const input = document.getElementById("message");
    const messages = document.getElementById("messages");
    const send = document.getElementById("send");
    const status = document.getElementById("status");
    const threadKey = "digital-lindaiyu-thread-id";
    let threadId = localStorage.getItem(threadKey) || "";

    function addMessage(text, role, className = "") {
      const bubble = document.createElement("div");
      bubble.className = `bubble ${role} ${className}`.trim();
      bubble.textContent = text;
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
      return bubble;
    }

    async function sendMessage(text) {
      status.textContent = "应答中";
      send.disabled = true;
      const pending = addMessage("...", "assistant");
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({message: text, thread_id: threadId})
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "请求失败");
        }
        threadId = data.thread_id;
        localStorage.setItem(threadKey, threadId);
        pending.textContent = data.reply || "无言。";
      } catch (error) {
        pending.textContent = error.message || "请求失败";
        pending.classList.add("error");
      } finally {
        status.textContent = "在线";
        send.disabled = false;
        input.focus();
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text || send.disabled) return;
      addMessage(text, "user");
      input.value = "";
      sendMessage(text);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    run()
