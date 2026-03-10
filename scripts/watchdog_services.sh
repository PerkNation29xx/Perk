#!/bin/zsh
set -u

ROOT_DIR="/Users/nation/Documents/New project/PerkNationBackend"
WATCHDOG_DIR="$ROOT_DIR/watchdog"
mkdir -p "$WATCHDOG_DIR"

log() {
  local message="$1"
  print -r -- "$(date -u +"%Y-%m-%dT%H:%M:%SZ") $message" >> "$WATCHDOG_DIR/watchdog.log"
}

log "Watchdog tick"

is_http_healthy() {
  curl -fsS --max-time 4 "http://127.0.0.1:8000/v1/health" >/dev/null 2>&1
}

is_https_healthy() {
  curl -kfsS --max-time 4 "https://127.0.0.1:8443/v1/health" >/dev/null 2>&1
}

is_ollama_healthy() {
  curl -fsS --max-time 4 "http://127.0.0.1:11434/api/version" >/dev/null 2>&1
}

wait_for_health() {
  local target="$1"
  local timeout_seconds="${2:-20}"
  local waited=0

  while (( waited < timeout_seconds )); do
    case "$target" in
      http)
        is_http_healthy && return 0
        ;;
      https)
        is_https_healthy && return 0
        ;;
      ollama)
        is_ollama_healthy && return 0
        ;;
      *)
        return 1
        ;;
    esac
    sleep 1
    (( waited += 1 ))
  done

  return 1
}

kill_listener_on_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    kill $pids >/dev/null 2>&1 || true
    sleep 1
  fi
}

start_http() {
  log "Starting HTTP API on :8000"
  (
    cd "$ROOT_DIR" || exit 1
    nohup "$ROOT_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 \
      >> "$ROOT_DIR/uvicorn_http.out.log" 2>> "$ROOT_DIR/uvicorn_http.err.log" &
    print -r -- "$!" > "$ROOT_DIR/uvicorn_http.pid"
  )
}

start_https() {
  log "Starting HTTPS API/Web on :8443"
  (
    cd "$ROOT_DIR" || exit 1
    nohup "$ROOT_DIR/scripts/run_local_https.sh" \
      >> "$ROOT_DIR/uvicorn.out.log" 2>> "$ROOT_DIR/uvicorn.err.log" &
    print -r -- "$!" > "$ROOT_DIR/uvicorn.pid"
  )
}

start_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    log "Ollama binary not found in PATH"
    return 1
  fi

  log "Starting Ollama on :11434"
  nohup ollama serve >> "$ROOT_DIR/ollama.out.log" 2>> "$ROOT_DIR/ollama.err.log" &
  print -r -- "$!" > "$ROOT_DIR/ollama.pid"
}

ensure_http() {
  if is_http_healthy; then
    return 0
  fi

  log "HTTP healthcheck failed; restarting :8000"
  kill_listener_on_port 8000
  start_http

  if wait_for_health http 20; then
    log "HTTP recovered on :8000"
  else
    log "HTTP still unhealthy on :8000"
  fi
}

ensure_https() {
  if is_https_healthy; then
    return 0
  fi

  log "HTTPS healthcheck failed; restarting :8443"
  kill_listener_on_port 8443
  start_https

  if wait_for_health https 25; then
    log "HTTPS recovered on :8443"
  else
    log "HTTPS still unhealthy on :8443"
  fi
}

ensure_ollama() {
  if is_ollama_healthy; then
    return 0
  fi

  log "Ollama healthcheck failed; restarting :11434"
  kill_listener_on_port 11434
  start_ollama || return 0

  if wait_for_health ollama 15; then
    log "Ollama recovered on :11434"
  else
    log "Ollama still unhealthy on :11434"
  fi
}

ensure_http
ensure_https
ensure_ollama
