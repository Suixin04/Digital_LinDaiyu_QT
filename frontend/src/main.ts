import "./styles.css";

type HealthResponse = {
  status: string;
  model: string;
  llm_configured: boolean;
  retrieval_enabled: boolean;
  tts_backend: string;
  tts_enabled: boolean;
};

type ChatResponse = {
  reply: string;
  thread_id: string;
  audio_url?: string | null;
  audio_error?: string | null;
};

type StreamPayload = {
  delta?: string;
  detail?: string;
  job_id?: string;
  reply?: string;
  text?: string;
  thread_id?: string;
  url?: string;
};

type TTSStatusResponse = {
  backend: string;
  enabled: boolean;
  ready: boolean;
  base_url?: string | null;
};

type MessageRole = "assistant" | "user";

const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const threadKey = "digital-lindaiyu-thread-id";
let threadId = localStorage.getItem(threadKey) || "";
let ttsEnabled = false;
let sending = false;
let audioPlaying = false;
const audioQueue: string[] = [];

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("App container missing");
}

app.innerHTML = `
  <div class="shell">
    <header class="topbar">
      <div>
        <h1>数字林黛玉</h1>
        <div class="meta" id="meta">连接中</div>
      </div>
      <div class="controls">
        <label class="voice-toggle">
          <input id="voice" type="checkbox" />
          <span>语音</span>
        </label>
        <div class="status" id="status">连接中</div>
      </div>
    </header>
    <main class="chat-panel">
      <div class="messages" id="messages" aria-live="polite">
        <div class="bubble assistant">风露清愁，已在潇湘馆候着。你来了，便说说今日心事罢。</div>
      </div>
    </main>
    <form class="composer" id="form">
      <textarea id="message" name="message" rows="2" maxlength="4000" placeholder="写一句话寄给黛玉..."></textarea>
      <button id="send" type="submit">发送</button>
    </form>
    <audio id="player" preload="auto" playsinline></audio>
  </div>
`;

document.documentElement.style.setProperty(
  "--background-image",
  `url("${apiUrl("/assets/background.jpg")}")`
);

const form = requireElement<HTMLFormElement>("#form");
const input = requireElement<HTMLTextAreaElement>("#message");
const messages = requireElement<HTMLDivElement>("#messages");
const send = requireElement<HTMLButtonElement>("#send");
const status = requireElement<HTMLDivElement>("#status");
const meta = requireElement<HTMLDivElement>("#meta");
const voice = requireElement<HTMLInputElement>("#voice");
const player = requireElement<HTMLAudioElement>("#player");

void refreshStatus();

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || sending) return;
  addMessage(text, "user");
  input.value = "";
  void sendMessage(text);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

voice.addEventListener("change", () => {
  if (voice.checked && !ttsEnabled) {
    voice.checked = false;
    setStatus("语音不可用", "warn");
  }
});

player.addEventListener("ended", () => {
  void playNextAudio();
});
player.addEventListener("error", () => {
  setStatus("语音失败", "warn");
  void playNextAudio();
});

async function refreshStatus(): Promise<void> {
  try {
    const [health, tts] = await Promise.all([
      request<HealthResponse>("/health"),
      request<TTSStatusResponse>("/api/tts/status")
    ]);
    ttsEnabled = Boolean(tts.enabled);
    voice.disabled = !ttsEnabled;
    meta.textContent = [
      health.model,
      health.retrieval_enabled ? "RAG" : "无检索",
      tts.enabled ? `TTS ${tts.backend}` : "文字"
    ].join(" / ");
    setStatus(health.llm_configured ? "在线" : "离线回复", health.llm_configured ? "ok" : "warn");
  } catch {
    voice.disabled = true;
    setStatus("后端离线", "error");
    meta.textContent = "未连接";
  }
}

async function sendMessage(text: string): Promise<void> {
  sending = true;
  send.disabled = true;
  voice.disabled = voice.disabled || !ttsEnabled;
  setStatus("应答中", "busy");
  const pending = addMessage("", "assistant");
  try {
    await streamChat(text, pending);
    if (!pending.textContent) {
      pending.textContent = "无言。";
    }
    if (!audioPlaying && audioQueue.length === 0) {
      setStatus("在线", "ok");
    }
  } catch (error) {
    pending.textContent = error instanceof Error ? error.message : "请求失败";
    pending.classList.add("error");
    setStatus("请求失败", "error");
  } finally {
    sending = false;
    send.disabled = false;
    voice.disabled = !ttsEnabled;
    input.focus();
  }
}

async function streamChat(text: string, pending: HTMLDivElement): Promise<void> {
  const response = await fetch(apiUrl("/api/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      thread_id: threadId,
      speak: voice.checked && ttsEnabled
    })
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || data?.message || "请求失败");
  }
  if (!response.body) {
    throw new Error("浏览器不支持流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      buffer = consumeSseBuffer(buffer, pending);
    }
    if (done) break;
  }
  consumeSseBuffer(`${buffer}\n\n`, pending);
}

function addMessage(text: string, role: MessageRole): HTMLDivElement {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function enqueueAudio(audioUrl: string): void {
  audioQueue.push(audioUrl);
  if (!audioPlaying) {
    void playNextAudio();
  }
}

async function playNextAudio(): Promise<void> {
  const audioUrl = audioQueue.shift();
  if (!audioUrl) {
    audioPlaying = false;
    setStatus("在线", "ok");
    return;
  }
  audioPlaying = true;
  player.src = apiUrl(audioUrl);
  try {
    await player.play();
    setStatus("播放中", "ok");
  } catch (error) {
    audioPlaying = false;
    setStatus("点击页面后播放", "warn");
    document.addEventListener(
      "click",
      () => {
        audioQueue.unshift(audioUrl);
        if (!audioPlaying) {
          void playNextAudio();
        }
      },
      { once: true }
    );
    console.warn("Audio playback was blocked", error);
  }
}

function consumeSseBuffer(buffer: string, pending: HTMLDivElement): string {
  const events = buffer.split(/\n\n/);
  const rest = events.pop() || "";
  for (const raw of events) {
    handleSseEvent(raw, pending);
  }
  return rest;
}

function handleSseEvent(raw: string, pending: HTMLDivElement): void {
  if (!raw.trim()) return;
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  const data = parsePayload(dataLines.join("\n"));
  if (event === "start" && data.thread_id) {
    threadId = data.thread_id;
    localStorage.setItem(threadKey, threadId);
    return;
  }
  if (event === "text") {
    pending.textContent += data.delta || "";
    messages.scrollTop = messages.scrollHeight;
    return;
  }
  if (event === "audio" && data.url) {
    setStatus(audioPlaying ? "播放中" : "语音生成中", "busy");
    enqueueAudio(data.url);
    return;
  }
  if (event === "tts_error") {
    setStatus("语音失败", "warn");
    return;
  }
  if (event === "done") {
    if (data.thread_id) {
      threadId = data.thread_id;
      localStorage.setItem(threadKey, threadId);
    }
    if (!pending.textContent && data.reply) {
      pending.textContent = data.reply;
    }
    return;
  }
  if (event === "error") {
    pending.textContent = data.detail || "请求失败";
    pending.classList.add("error");
    setStatus("请求失败", "error");
  }
}

function parsePayload(data: string): StreamPayload {
  if (!data) return {};
  try {
    return JSON.parse(data) as StreamPayload;
  } catch {
    return {};
  }
}

function setStatus(text: string, state: "ok" | "busy" | "warn" | "error"): void {
  status.textContent = text;
  status.dataset.state = state;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail || data?.message || "请求失败";
    throw new Error(detail);
  }
  return data as T;
}

function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
}

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) {
    throw new Error(`Missing element: ${selector}`);
  }
  return element;
}
