#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST_ARG=""
PORT_ARG=""
TTS_MODE="none"
PRETRAINED_MODELS_ARG=""
FRONTEND_MODE_ARG=""
FRONTEND_HOST_ARG=""
FRONTEND_PORT_ARG=""
FRONTEND_INSTALL=1
FRONTEND_MODE=""
FRONTEND_PID=""
SYNC_DEPS=1
INIT_SUBMODULE=1
LOAD_KB=1
REBUILD_KB=0

log() {
  printf '[digital-lindaiyu] %s\n' "$*"
}

die() {
  printf '[digital-lindaiyu] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/start_web.sh [options]

Options:
  --host HOST              Bind address, default from .env or 0.0.0.0.
  --port PORT              Bind port, default from PORT/.env or 8000.
  --tts MODE               TTS mode: none, gpt_sovits, cosyvoice, or env.
                           Default is none for server deployment.
  --with-tts               Shortcut for --tts gpt_sovits.
  --no-tts                 Shortcut for --tts none.
  --pretrained-models DIR   Override GPT-SoVITS pretrained_models directory.
  --frontend MODE          Frontend mode: dev, preview, build, or none.
                           Default is dev.
  --frontend-host HOST     Frontend bind address, default from .env or 0.0.0.0.
  --frontend-port PORT     Frontend port, default from .env or 5173.
  --no-frontend-install    Do not run npm install before frontend start/build.
  --rebuild-kb             Rebuild the Chroma knowledge base before start.
  --skip-kb                Do not load/update the knowledge base.
  --no-sync                Do not run uv sync before start.
  --no-submodule           Do not run git submodule update.
  -h, --help               Show this help.

Examples:
  bash scripts/start_web.sh
  bash scripts/start_web.sh --host 0.0.0.0 --port 8000
  bash scripts/start_web.sh --frontend none
  bash scripts/start_web.sh --frontend build
  bash scripts/start_web.sh --rebuild-kb
  bash scripts/start_web.sh --tts gpt_sovits --pretrained-models "$HOME/Downloads/pretrained_models"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || die "--host requires a value"
      HOST_ARG="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || die "--port requires a value"
      PORT_ARG="$2"
      shift 2
      ;;
    --tts)
      [[ $# -ge 2 ]] || die "--tts requires one of: none, gpt_sovits, cosyvoice, env"
      TTS_MODE="$2"
      shift 2
      ;;
    --with-tts)
      TTS_MODE="gpt_sovits"
      shift
      ;;
    --no-tts)
      TTS_MODE="none"
      shift
      ;;
    --pretrained-models)
      [[ $# -ge 2 ]] || die "--pretrained-models requires a directory"
      PRETRAINED_MODELS_ARG="$2"
      shift 2
      ;;
    --frontend)
      [[ $# -ge 2 ]] || die "--frontend requires one of: dev, preview, build, none"
      FRONTEND_MODE_ARG="$2"
      shift 2
      ;;
    --frontend-host)
      [[ $# -ge 2 ]] || die "--frontend-host requires a value"
      FRONTEND_HOST_ARG="$2"
      shift 2
      ;;
    --frontend-port)
      [[ $# -ge 2 ]] || die "--frontend-port requires a value"
      FRONTEND_PORT_ARG="$2"
      shift 2
      ;;
    --no-frontend-install)
      FRONTEND_INSTALL=0
      shift
      ;;
    --rebuild-kb)
      REBUILD_KB=1
      LOAD_KB=1
      shift
      ;;
    --skip-kb)
      LOAD_KB=0
      shift
      ;;
    --no-sync)
      SYNC_DEPS=0
      shift
      ;;
    --no-submodule)
      INIT_SUBMODULE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "unknown option: $1"
      ;;
  esac
done

case "$TTS_MODE" in
  none|gpt_sovits|cosyvoice|env) ;;
  off|false|0) TTS_MODE="none" ;;
  *) die "--tts must be one of: none, gpt_sovits, cosyvoice, env" ;;
esac

if [[ -n "$FRONTEND_MODE_ARG" ]]; then
  case "$FRONTEND_MODE_ARG" in
    dev|preview|build|none) ;;
    off|false|0) FRONTEND_MODE_ARG="none" ;;
    *) die "--frontend must be one of: dev, preview, build, none" ;;
  esac
fi

load_env_file() {
  local file="$1"
  local line key value first last
  [[ -f "$file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#export }"
    [[ "$line" == *"="* ]] || continue

    key="${line%%=*}"
    value="${line#*=}"
    key="$(printf '%s' "$key" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')"

    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ "$first$last" == '""' || "$first$last" == "''" ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi

    if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$file"
}

ensure_env_file() {
  if [[ ! -f "$ROOT_DIR/.env" && -f "$ROOT_DIR/.env.server.example" ]]; then
    cp "$ROOT_DIR/.env.server.example" "$ROOT_DIR/.env"
    log "created .env from .env.server.example; edit DEEPSEEK_API_KEY for online chat"
  fi
  load_env_file "$ROOT_DIR/.env"
}

ensure_uv_layout() {
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"
  export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT_DIR/.uv-python}"
  export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$ROOT_DIR/.venv}"
  export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
  export HF_HOME="${HF_HOME:-$ROOT_DIR/.hf-cache}"
  export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
  export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
  export FASTEMBED_CACHE_DIR="${FASTEMBED_CACHE_DIR:-$ROOT_DIR/.model-cache/fastembed}"
  export npm_config_cache="${npm_config_cache:-$ROOT_DIR/.npm-cache}"
}

ensure_uv_available() {
  command -v uv >/dev/null 2>&1 || die "uv is required. Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
}

load_node_env() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    return 0
  fi
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
  fi
}

ensure_submodule() {
  [[ "$INIT_SUBMODULE" -eq 1 ]] || return 0
  [[ -f "$ROOT_DIR/.gitmodules" && -d "$ROOT_DIR/.git" ]] || return 0
  command -v git >/dev/null 2>&1 || die "git is required to initialize submodules"
  log "checking submodules"
  git submodule update --init --recursive
}

sync_deps() {
  [[ "$SYNC_DEPS" -eq 1 ]] || return 0
  log "syncing Python environment with uv"
  uv sync --frozen --extra local-embeddings --extra knowledge
}

configure_runtime_env() {
  local selected_tts

  if [[ -n "$HOST_ARG" ]]; then
    export DIGITAL_LDY_WEB_HOST="$HOST_ARG"
  else
    export DIGITAL_LDY_WEB_HOST="${DIGITAL_LDY_WEB_HOST:-0.0.0.0}"
  fi

  if [[ -n "$PORT_ARG" ]]; then
    export DIGITAL_LDY_WEB_PORT="$PORT_ARG"
    export PORT="$PORT_ARG"
  else
    export DIGITAL_LDY_WEB_PORT="${PORT:-${DIGITAL_LDY_WEB_PORT:-8000}}"
    export PORT="$DIGITAL_LDY_WEB_PORT"
  fi

  export EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-fastembed}"
  FRONTEND_MODE="${FRONTEND_MODE_ARG:-${DIGITAL_LDY_FRONTEND_MODE:-dev}}"
  case "$FRONTEND_MODE" in
    dev|preview|build|none) ;;
    off|false|0) FRONTEND_MODE="none" ;;
    *) die "DIGITAL_LDY_FRONTEND_MODE must be one of: dev, preview, build, none" ;;
  esac
  if [[ -n "$FRONTEND_HOST_ARG" ]]; then
    export DIGITAL_LDY_FRONTEND_HOST="$FRONTEND_HOST_ARG"
  else
    export DIGITAL_LDY_FRONTEND_HOST="${DIGITAL_LDY_FRONTEND_HOST:-0.0.0.0}"
  fi
  if [[ -n "$FRONTEND_PORT_ARG" ]]; then
    export DIGITAL_LDY_FRONTEND_PORT="$FRONTEND_PORT_ARG"
  else
    export DIGITAL_LDY_FRONTEND_PORT="${DIGITAL_LDY_FRONTEND_PORT:-5173}"
  fi
  if [[ -n "$PRETRAINED_MODELS_ARG" ]]; then
    if [[ "$PRETRAINED_MODELS_ARG" = /* ]]; then
      export GPT_SOVITS_PRETRAINED_MODELS_DIR="$PRETRAINED_MODELS_ARG"
    else
      export GPT_SOVITS_PRETRAINED_MODELS_DIR="$ROOT_DIR/$PRETRAINED_MODELS_ARG"
    fi
  fi

  if [[ "$TTS_MODE" == "env" ]]; then
    selected_tts="${TTS_BACKEND:-none}"
  else
    selected_tts="$TTS_MODE"
  fi
  export TTS_BACKEND="$selected_tts"
  if [[ "$selected_tts" == "none" ]]; then
    export GPT_SOVITS_AUTO_START=0
  fi
}

ensure_node_available() {
  [[ "$FRONTEND_MODE" != "none" ]] || return 0
  load_node_env
  command -v node >/dev/null 2>&1 || die "node is required for the frontend"
  command -v npm >/dev/null 2>&1 || die "npm is required for the frontend"
}

sync_frontend_deps() {
  [[ "$FRONTEND_MODE" != "none" ]] || return 0
  [[ "$FRONTEND_INSTALL" -eq 1 ]] || return 0
  if [[ -d "$ROOT_DIR/frontend/node_modules" ]]; then
    return 0
  fi
  log "installing frontend dependencies"
  if [[ -f "$ROOT_DIR/frontend/package-lock.json" ]]; then
    npm --prefix "$ROOT_DIR/frontend" ci
  else
    npm --prefix "$ROOT_DIR/frontend" install
  fi
}

backend_proxy_target() {
  local proxy_host="$DIGITAL_LDY_WEB_HOST"
  if [[ "$proxy_host" == "0.0.0.0" || "$proxy_host" == "::" || -z "$proxy_host" ]]; then
    proxy_host="127.0.0.1"
  fi
  printf 'http://%s:%s' "$proxy_host" "$DIGITAL_LDY_WEB_PORT"
}

start_frontend() {
  case "$FRONTEND_MODE" in
    none)
      log "frontend disabled"
      ;;
    build)
      log "building frontend"
      VITE_API_BASE_URL="${VITE_API_BASE_URL:-}" npm --prefix "$ROOT_DIR/frontend" run build
      ;;
    dev)
      log "starting frontend dev server on ${DIGITAL_LDY_FRONTEND_HOST}:${DIGITAL_LDY_FRONTEND_PORT}"
      VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-$(backend_proxy_target)}" \
        npm --prefix "$ROOT_DIR/frontend" run dev -- \
        --host "$DIGITAL_LDY_FRONTEND_HOST" \
        --port "$DIGITAL_LDY_FRONTEND_PORT" &
      FRONTEND_PID=$!
      ;;
    preview)
      log "building frontend"
      VITE_API_BASE_URL="${VITE_API_BASE_URL:-}" npm --prefix "$ROOT_DIR/frontend" run build
      log "starting frontend preview on ${DIGITAL_LDY_FRONTEND_HOST}:${DIGITAL_LDY_FRONTEND_PORT}"
      VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-$(backend_proxy_target)}" \
        npm --prefix "$ROOT_DIR/frontend" run preview -- \
        --host "$DIGITAL_LDY_FRONTEND_HOST" \
        --port "$DIGITAL_LDY_FRONTEND_PORT" &
      FRONTEND_PID=$!
      ;;
  esac
}

cleanup() {
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
    wait "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

validate_tts() {
  case "$TTS_BACKEND" in
    none)
      log "TTS disabled"
      ;;
    cosyvoice)
      if [[ -z "${DASHSCOPE_API_KEY:-${ALIYUN_API_KEY:-}}" ]]; then
        die "TTS_BACKEND=cosyvoice requires DASHSCOPE_API_KEY"
      fi
      log "CosyVoice TTS selected"
      ;;
    gpt_sovits)
      local gsv_dir="${GPT_SOVITS_DIR:-GPT-SoVITS}"
      local gpt_weights="${GPT_SOVITS_GPT_WEIGHTS:-GPT_weights_v4/digital_ldy-e15.ckpt}"
      local sovits_weights="${GPT_SOVITS_SOVITS_WEIGHTS:-SoVITS_weights_v4/digital_ldy_e4_s156_l64.pth}"
      local pretrained_dir="${GPT_SOVITS_PRETRAINED_MODELS_DIR:-}"
      [[ -f "$ROOT_DIR/$gsv_dir/api_v2.py" ]] || die "GPT-SoVITS submodule is missing api_v2.py; run git submodule update --init --recursive"
      if [[ -n "$pretrained_dir" ]]; then
        [[ -d "$pretrained_dir" ]] || die "pretrained models directory does not exist: $pretrained_dir"
        [[ -d "$pretrained_dir/chinese-roberta-wwm-ext-large" ]] || die "missing pretrained model directory: $pretrained_dir/chinese-roberta-wwm-ext-large"
        [[ -d "$pretrained_dir/chinese-hubert-base" ]] || die "missing pretrained model directory: $pretrained_dir/chinese-hubert-base"
        log "using GPT-SoVITS pretrained models from $pretrained_dir"
      fi
      if [[ "${GPT_SOVITS_AUTO_START:-1}" != "0" ]]; then
        [[ -f "$ROOT_DIR/$gsv_dir/$gpt_weights" ]] || die "missing GPT weights: $gsv_dir/$gpt_weights"
        [[ -f "$ROOT_DIR/$gsv_dir/$sovits_weights" ]] || die "missing SoVITS weights: $gsv_dir/$sovits_weights"
      fi
      log "GPT-SoVITS TTS selected"
      ;;
    *)
      die "unknown TTS_BACKEND: $TTS_BACKEND"
      ;;
  esac
}

load_knowledge_base() {
  [[ "$LOAD_KB" -eq 1 ]] || return 0
  if [[ "$REBUILD_KB" -eq 1 ]]; then
    log "rebuilding knowledge base"
    uv run python -m scripts.load_kb --rebuild
  else
    log "updating knowledge base"
    uv run python -m scripts.load_kb
  fi
}

warn_missing_llm_key() {
  if [[ -z "${CHAT_API_KEY:-${DEEPSEEK_API_KEY:-${OPENAI_API_KEY:-}}}" ]]; then
    log "DEEPSEEK_API_KEY is empty; service will start, but replies use the offline placeholder"
  fi
}

start_server() {
  log "starting backend API on ${DIGITAL_LDY_WEB_HOST}:${DIGITAL_LDY_WEB_PORT}"
  uv run python server.py
}

ensure_env_file
ensure_uv_layout
ensure_uv_available
ensure_submodule
sync_deps
configure_runtime_env
ensure_node_available
sync_frontend_deps
validate_tts
load_knowledge_base
warn_missing_llm_key
trap cleanup EXIT INT TERM
start_frontend
start_server
