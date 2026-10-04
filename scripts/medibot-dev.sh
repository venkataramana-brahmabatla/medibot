#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="$ROOT_DIR/logs"
RUNTIME_DIR="$ROOT_DIR/.medibot"
BACKEND_LOG="$LOG_DIR/fastapi.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID_FILE="$RUNTIME_DIR/fastapi.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

log() {
  printf '[medibot] %s\n' "$*"
}

port_pids() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true
}

wait_for_port() {
  local name="$1"
  local port="$2"

  for _ in {1..40}; do
    if [[ -n "$(port_pids "$port")" ]]; then
      log "$name is ready on port $port."
      return
    fi
    sleep 0.25
  done

  log "$name did not become ready on port $port. Check the service log."
  return 1
}

stop_pid() {
  local pid="$1"

  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}

stop_service() {
  local name="$1"
  local port="$2"
  local pid_file="$3"
  local pids=()
  local pid

  if [[ -f "$pid_file" ]]; then
    pid="$(<"$pid_file")"
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      pids+=("$pid")
    fi
    rm -f "$pid_file"
  fi

  while read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(port_pids "$port")

  if ((${#pids[@]} == 0)); then
    log "$name is not running."
    return
  fi

  local unique_pid
  while read -r unique_pid; do
    [[ -n "$unique_pid" ]] || continue
    log "Stopping $name (PID $unique_pid)..."
    stop_pid "$unique_pid"
  done < <(printf '%s\n' "${pids[@]}" | sort -u)

  for _ in {1..20}; do
    if [[ -z "$(port_pids "$port")" ]]; then
      log "$name stopped."
      return
    fi
    sleep 0.25
  done

  while read -r pid; do
    [[ -n "$pid" ]] || continue
    log "$name did not stop gracefully; terminating PID $pid."
    kill -9 "$pid" 2>/dev/null || true
  done < <(port_pids "$port")
}

stop_services() {
  stop_service "FastAPI" "$BACKEND_PORT" "$BACKEND_PID_FILE"
  stop_service "Next.js" "$FRONTEND_PORT" "$FRONTEND_PID_FILE"
}

start_services() {
  local python_bin="$ROOT_DIR/venv/bin/python"

  if [[ ! -x "$python_bin" ]]; then
    log "Missing Python virtualenv at $python_bin"
    log "Create it first with: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
  fi

  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    log "Missing frontend dependencies. Installing with npm install..."
    (cd "$ROOT_DIR/frontend" && npm install)
  fi

  log "Starting FastAPI on http://localhost:$BACKEND_PORT..."
  (
    cd "$ROOT_DIR"
    nohup "$python_bin" -m src.api.main >"$BACKEND_LOG" 2>&1 &
    echo "$!" >"$BACKEND_PID_FILE"
  )

  log "Starting Next.js on http://localhost:$FRONTEND_PORT..."
  (
    cd "$ROOT_DIR/frontend"
    nohup npm run dev -- --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
    echo "$!" >"$FRONTEND_PID_FILE"
  )

  wait_for_port "FastAPI" "$BACKEND_PORT"
  wait_for_port "Next.js" "$FRONTEND_PORT"
  log "FastAPI log: $BACKEND_LOG"
  log "Frontend log: $FRONTEND_LOG"
}

status_services() {
  local backend_pids frontend_pids
  backend_pids="$(port_pids "$BACKEND_PORT")"
  frontend_pids="$(port_pids "$FRONTEND_PORT")"

  if [[ -n "$backend_pids" ]]; then
    log "FastAPI is running on port $BACKEND_PORT (PID(s): ${backend_pids//$'\n'/, })."
  else
    log "FastAPI is stopped."
  fi

  if [[ -n "$frontend_pids" ]]; then
    log "Next.js is running on port $FRONTEND_PORT (PID(s): ${frontend_pids//$'\n'/, })."
  else
    log "Next.js is stopped."
  fi
}

command="${1:-restart}"
case "$command" in
  start)
    stop_services
    start_services
    ;;
  restart)
    stop_services
    start_services
    ;;
  stop)
    stop_services
    ;;
  status)
    status_services
    ;;
  *)
    printf 'Usage: %s [start|restart|stop|status]\n' "$0" >&2
    exit 2
    ;;
esac
