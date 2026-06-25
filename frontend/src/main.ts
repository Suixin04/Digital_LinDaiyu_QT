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
    <audio id="player" preload="none"></audio>
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

player.addEventListener("ended", () => setStatus("在线", "ok"));
player.addEventListener("error", () => setStatus("语音失败", "warn"));

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
  const pending = addMessage("...", "assistant");
  try {
    const data = await request<ChatResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        thread_id: threadId,
        speak: voice.checked && ttsEnabled
      })
    });
    threadId = data.thread_id;
    localStorage.setItem(threadKey, threadId);
    pending.textContent = data.reply || "无言。";
    if (data.audio_url) {
      await playAudio(data.audio_url);
    } else if (data.audio_error) {
      setStatus("语音失败", "warn");
    } else {
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

function addMessage(text: string, role: MessageRole): HTMLDivElement {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

async function playAudio(audioUrl: string): Promise<void> {
  player.src = apiUrl(audioUrl);
  try {
    await player.play();
    setStatus("播放中", "ok");
  } catch {
    setStatus("在线", "ok");
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
