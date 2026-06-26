"""FastAPI backend for the separated Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import shutil
import threading
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Deque, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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
from .tts.base import TTSError, clean_for_tts
from .tts.gpt_sovits import start_tts_server, stop_tts_process

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


class AudioStreamJob:
    """Buffered audio stream produced by the sequential TTS worker."""

    def __init__(self, text: str) -> None:
        self.id = uuid.uuid4().hex
        self.text = text
        self._chunks: list[bytes] = []
        self._done = False
        self._error: str | None = None
        self._condition = threading.Condition()

    @property
    def done(self) -> bool:
        with self._condition:
            return self._done

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._condition:
            self._chunks.append(chunk)
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self._done = True
            self._condition.notify_all()

    def fail(self, message: str) -> None:
        with self._condition:
            self._error = message
            self._done = True
            self._condition.notify_all()

    def iter_chunks(self) -> Iterator[bytes]:
        index = 0
        while True:
            with self._condition:
                while index >= len(self._chunks) and not self._done:
                    self._condition.wait(timeout=30)
                if index < len(self._chunks):
                    chunk = self._chunks[index]
                    index += 1
                elif self._error:
                    logger.warning("TTS stream job %s failed: %s", self.id, self._error)
                    return
                else:
                    return
            yield chunk


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

    def stream_reply(
        self,
        message: str,
        thread_id: str,
        on_chunk,
        on_sentence,
    ) -> str:
        with self._lock:
            return self._get_engine().stream(
                message,
                thread_id=thread_id,
                on_chunk=on_chunk,
                on_sentence=on_sentence,
            )

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
        self._tts_lock = threading.RLock()
        self._files: Deque[Path] = deque()
        self._audio_dir = resolve_project_path("runtime/audio")
        self._stream_jobs: dict[str, AudioStreamJob] = {}
        self._stream_order: Deque[str] = deque()
        self._stream_queue: queue.Queue[AudioStreamJob | None] = queue.Queue()
        self._stream_worker_started = False
        self._stream_worker_lock = threading.RLock()

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
        with self._tts_lock:
            client = self._ensure_client()
            path = client.synthesize(spoken)
            if not path:
                raise HTTPException(status_code=503, detail="TTS synthesis failed")
            return self._publish_audio(Path(path))

    def enqueue_stream(self, text: str) -> AudioStreamJob | None:
        spoken = clean_for_tts(text).strip()
        if not spoken:
            return None
        if get_tts_config().backend == "none":
            raise HTTPException(status_code=503, detail="TTS is disabled")

        job = AudioStreamJob(spoken)
        with self._lock:
            self._stream_jobs[job.id] = job
            self._stream_order.append(job.id)
            while len(self._stream_order) > 100:
                old_id = self._stream_order.popleft()
                old_job = self._stream_jobs.get(old_id)
                if old_job is None or old_job.done:
                    self._stream_jobs.pop(old_id, None)
                else:
                    self._stream_order.appendleft(old_id)
                    break
        self._ensure_stream_worker()
        self._stream_queue.put(job)
        return job

    def get_stream_job(self, job_id: str) -> AudioStreamJob | None:
        with self._lock:
            return self._stream_jobs.get(job_id)

    def close(self) -> None:
        with self._lock:
            if self._stream_worker_started:
                self._stream_queue.put(None)
                self._stream_worker_started = False
            if self._client is not None:
                self._client.close()
                self._client = None
            if self._process is not None:
                stop_tts_process(self._process)
                self._process = None

    def _ensure_stream_worker(self) -> None:
        with self._stream_worker_lock:
            if self._stream_worker_started:
                return
            worker = threading.Thread(
                target=self._stream_worker,
                name="digital-lindaiyu-tts-stream",
                daemon=True,
            )
            worker.start()
            self._stream_worker_started = True

    def _stream_worker(self) -> None:
        while True:
            job = self._stream_queue.get()
            if job is None:
                return
            try:
                self._run_stream_job(job)
                job.finish()
            except Exception as e:  # noqa: BLE001
                logger.exception("TTS stream job failed")
                job.fail(str(e))

    def _run_stream_job(self, job: AudioStreamJob) -> None:
        with self._tts_lock:
            client = self._ensure_client()
            stream = getattr(client, "stream", None)
            if callable(stream):
                sent = False
                for chunk in stream(job.text):
                    sent = True
                    job.append(chunk)
                if not sent:
                    raise TTSError("TTS stream returned no audio")
                return

            path = client.synthesize(job.text)
            if not path:
                raise TTSError("TTS synthesis failed")
            source = Path(path)
            if not source.exists():
                raise TTSError("TTS audio file missing")
            try:
                with source.open("rb") as f:
                    while True:
                        chunk = f.read(32768)
                        if not chunk:
                            break
                        job.append(chunk)
            finally:
                try:
                    source.unlink()
                except OSError:
                    pass

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
                stop_tts_process(self._process)
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


def _sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    thread_id = _normalize_thread_id(request.thread_id)
    events: queue.Queue[str | None] = queue.Queue()

    def emit(event: str, payload: dict) -> None:
        events.put(_sse(event, payload))

    def on_chunk(delta: str) -> None:
        emit("text", {"delta": delta})

    def on_sentence(sentence: str) -> None:
        if not request.speak:
            return
        try:
            job = tts_service.enqueue_stream(sentence)
            if job is None:
                return
            emit(
                "audio",
                {
                    "job_id": job.id,
                    "url": f"/api/audio/stream/{job.id}",
                    "text": sentence,
                },
            )
        except HTTPException as e:
            emit("tts_error", {"detail": str(e.detail)})
        except Exception as e:  # noqa: BLE001
            logger.exception("failed to enqueue TTS stream")
            emit("tts_error", {"detail": str(e)})

    def run_chat() -> None:
        try:
            emit("start", {"thread_id": thread_id})
            reply = chat_service.stream_reply(
                message,
                thread_id,
                on_chunk=on_chunk,
                on_sentence=on_sentence,
            )
            emit("done", {"thread_id": thread_id, "reply": reply})
        except Exception as e:  # noqa: BLE001
            logger.exception("streaming chat failed")
            emit("error", {"detail": str(e)})
        finally:
            events.put(None)

    threading.Thread(
        target=run_chat,
        name="digital-lindaiyu-chat-stream",
        daemon=True,
    ).start()

    async def event_stream():
        while True:
            item = await asyncio.to_thread(events.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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


@app.get("/api/audio/stream/{job_id}", include_in_schema=False)
def audio_stream(job_id: str) -> StreamingResponse:
    job = tts_service.get_stream_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="audio stream not found")
    return StreamingResponse(job.iter_chunks(), media_type="audio/wav")


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
