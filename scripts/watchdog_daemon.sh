#!/bin/zsh
set -u

ROOT_DIR="/Users/nation/Documents/New project/PerkNationBackend"
WATCHDOG_DIR="$ROOT_DIR/watchdog"
PID_FILE="$WATCHDOG_DIR/watchdog_daemon.pid"
LOOP_LOG="$WATCHDOG_DIR/watchdog-loop.log"
LOOP_ERR="$WATCHDOG_DIR/watchdog-loop.err.log"
CHECK_SCRIPT="$ROOT_DIR/scripts/watchdog_services.sh"
INTERVAL_SECONDS="${PERKNATION_WATCHDOG_INTERVAL_SECONDS:-30}"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

mkdir -p "$WATCHDOG_DIR"

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

start_daemon() {
  if is_running; then
    echo "watchdog daemon already running (pid $(cat "$PID_FILE"))."
    return 0
  fi

  nohup "$SCRIPT_PATH" run >> "$LOOP_LOG" 2>> "$LOOP_ERR" &
  echo "$!" > "$PID_FILE"
  echo "watchdog daemon started (pid $(cat "$PID_FILE"))."
}

stop_daemon() {
  if ! is_running; then
    echo "watchdog daemon is not running."
    rm -f "$PID_FILE"
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  echo "watchdog daemon stopped."
}

status_daemon() {
  if is_running; then
    echo "watchdog daemon running (pid $(cat "$PID_FILE"))."
  else
    echo "watchdog daemon not running."
  fi
}

run_loop() {
  while true; do
    /bin/zsh "$CHECK_SCRIPT" || true
    sleep "$INTERVAL_SECONDS"
  done
}

case "${1:-start}" in
  start)
    start_daemon
    ;;
  stop)
    stop_daemon
    ;;
  restart)
    stop_daemon
    start_daemon
    ;;
  status)
    status_daemon
    ;;
  run)
    run_loop
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|run}"
    exit 1
    ;;
esac
