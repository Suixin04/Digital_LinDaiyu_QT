"""FastAPI backend for the separated Web UI."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Deque

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chat import ChatEngine
from .config import (
    env_flag,
    get_chat_model_config,
    get_gpt_sovits_config,
    get_tts_config,
)
from .logging_config import configure_app_logging
from .resources import resolve_project_path
from .tts import get_tts_client
from .tts.base import clean_for_tts
from .tts.gpt_sovits import start_tts_server

configure_app_logging()

logger = logging.getLogger(__name__)

AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=128)
    speak: bool = False


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    audio_url: str | None = None
    audio_error: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class TTSResponse(BaseModel):
    audio_url: str


class HealthResponse(BaseModel):
    status: str
    model: str
    llm_configured: bool
    retrieval_enabled: bool
    tts_backend: str
    tts_enabled: bool


class TTSStatusResponse(BaseModel):
    backend: str
    enabled: bool
    ready: bool
    auto_start: bool | None = None
    base_url: str | None = None


class ChatService:
    """Owns the shared ChatEngine used by HTTP requests."""

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

    def retrieval_enabled(self) -> bool:
        configured = env_flag("DIGITAL_LDY_ENABLE_RETRIEVAL", True)
        with self._lock:
            if self._engine is None:
                return configured
            return configured and self._engine.vector_store is not None


class TTSService:
    """Lazy TTS runtime for API synthesis requests."""

    def __init__(self) -> None:
        self._client = None
        self._process = None
        self._lock = threading.RLock()
        self._files: Deque[Path] = deque()
        self._audio_dir = resolve_project_path("runtime/audio")

    def status(self) -> TTSStatusResponse:
        cfg = get_tts_config()
        auto_start = None
        base_url = None
        if cfg.backend == "gpt_sovits":
            gsv = get_gpt_sovits_config()
            auto_start = gsv.auto_start
            base_url = gsv.base_url
        return TTSStatusResponse(
            backend=cfg.backend,
            enabled=cfg.backend != "none",
            ready=self._client is not None,
            auto_start=auto_start,
            base_url=base_url,
        )

    def synthesize(self, text: str) -> str:
        spoken = clean_for_tts(text).strip()
        if not spoken:
            raise HTTPException(status_code=400, detail="text is empty")
        with self._lock:
            client = self._ensure_client()
            path = client.synthesize(spoken)
            if not path:
                raise HTTPException(status_code=503, detail="TTS synthesis failed")
            return self._publish_audio(Path(path))

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
            if self._process is not None:
                self._process.terminate()
                self._process = None

    def _ensure_client(self):
        cfg = get_tts_config()
        if cfg.backend == "none":
            raise HTTPException(status_code=503, detail="TTS is disabled")
        if self._client is None:
            if cfg.backend == "gpt_sovits":
                self._process = start_tts_server(get_gpt_sovits_config())
            self._client = get_tts_client(cfg)
        if self._client is None:
            if self._process is not None:
                self._process.terminate()
                self._process = None
            raise HTTPException(status_code=503, detail="TTS is unavailable")
        return self._client

    def _publish_audio(self, source: Path) -> str:
        if not source.exists():
            raise HTTPException(status_code=503, detail="TTS audio file missing")
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        target = self._audio_dir / f"{uuid.uuid4().hex}{source.suffix or '.wav'}"
        shutil.copyfile(source, target)
        try:
            source.unlink()
        except OSError:
            pass
        self._files.append(target)
        while len(self._files) > 50:
            old = self._files.popleft()
            try:
                old.unlink()
            except OSError:
                pass
        return f"/api/audio/{target.name}"


chat_service = ChatService()
tts_service = TTSService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        tts_service.close()


app = FastAPI(
    title="Digital Lin Daiyu API",
    version="0.2.0",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    raw = os.getenv("DIGITAL_LDY_CORS_ORIGINS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

resources_dir = resolve_project_path("resources")
if resources_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(resources_dir)), name="assets")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "Digital Lin Daiyu API", "frontend": "Node/Vite"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    icon_path = resolve_project_path("resources/icon.ico")
    if not icon_path.exists():
        raise HTTPException(status_code=404, detail="favicon not found")
    return FileResponse(icon_path)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    config = get_chat_model_config()
    tts = get_tts_config()
    return HealthResponse(
        status="ok",
        model=config.model,
        llm_configured=config.is_available,
        retrieval_enabled=chat_service.retrieval_enabled(),
        tts_backend=tts.backend,
        tts_enabled=tts.backend != "none",
    )


@app.get("/api/tts/status", response_model=TTSStatusResponse)
def tts_status() -> TTSStatusResponse:
    return tts_service.status()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    thread_id = _normalize_thread_id(request.thread_id)
    reply = await run_in_threadpool(chat_service.reply, message, thread_id)
    audio_url = None
    audio_error = None
    if request.speak:
        try:
            audio_url = await run_in_threadpool(tts_service.synthesize, reply)
        except HTTPException as e:
            audio_error = str(e.detail)
        except Exception as e:  # noqa: BLE001
            logger.exception("TTS synthesis failed")
            audio_error = str(e)
    return ChatResponse(
        reply=reply,
        thread_id=thread_id,
        audio_url=audio_url,
        audio_error=audio_error,
    )


@app.post("/api/tts", response_model=TTSResponse)
async def synthesize_tts(request: TTSRequest) -> TTSResponse:
    audio_url = await run_in_threadpool(tts_service.synthesize, request.text)
    return TTSResponse(audio_url=audio_url)


@app.get("/api/audio/{audio_name}", include_in_schema=False)
def audio(audio_name: str) -> FileResponse:
    if "/" in audio_name or "\\" in audio_name:
        raise HTTPException(status_code=404, detail="audio not found")
    path = resolve_project_path("runtime/audio") / audio_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    media_type = AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


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
    uvicorn.run("digital_lindaiyu.api:app", host=host, port=port)


if __name__ == "__main__":
    run()
