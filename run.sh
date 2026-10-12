#!/usr/bin/env bash
# Control script for Health Copilot (backend + frontend).
#
#   ./run.sh start [backend|frontend]     start both (or one) in the background
#   ./run.sh stop [backend|frontend]      stop both (or one)
#   ./run.sh restart [backend|frontend]   stop, then start
#   ./run.sh status                       show what is running
#   ./run.sh logs [backend|frontend]      follow the logs
#   ./run.sh setup                        install backend and frontend dependencies
#
# Env: HOST=0.0.0.0 to open the site from another device (e.g. a phone camera on the same Wi-Fi),
#      RELOAD=1 to auto-reload the backend on code changes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"
HOST="${HOST:-127.0.0.1}"
BACKEND_PORT=8000
FRONTEND_PORT=5173
mkdir -p "$RUN"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
dim()   { printf '\033[2m%s\033[0m\n' "$*"; }

port_of() { [[ $1 == backend ]] && echo $BACKEND_PORT || echo $FRONTEND_PORT; }
url_of()  { [[ $1 == backend ]] && echo "http://127.0.0.1:$BACKEND_PORT/api/health" || echo "http://127.0.0.1:$FRONTEND_PORT/"; }

pid_of() {
  local f="$RUN/$1.pid"
  [[ -f $f ]] && kill -0 "$(cat "$f")" 2>/dev/null && cat "$f"
  return 0
}

# PIDs listening on the port that belong to this project (cwd inside the repo).
project_listeners() {
  local port=$1 pid
  for pid in $(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null); do
    [[ $(readlink "/proc/$pid/cwd" 2>/dev/null) == "$ROOT"* ]] && echo "$pid"
  done
  return 0
}

port_busy() { lsof -t -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

wait_up() {
  local name=$1 url i
  url=$(url_of "$name")
  for i in $(seq 1 60); do
    curl -s -o /dev/null --max-time 2 "$url" && return 0
    [[ -z $(pid_of "$name") ]] && return 1
    sleep 0.5
  done
  return 1
}

start_one() {
  local name=$1 port pid
  port=$(port_of "$name")
  if [[ -n $(pid_of "$name") ]]; then
    dim "$name already running (pid $(pid_of "$name"))"
    return 0
  fi
  if port_busy "$port"; then
    red "$name: port $port is already in use by pid $(lsof -t -iTCP:"$port" -sTCP:LISTEN | head -1). Run './run.sh stop' or free the port."
    return 1
  fi

  if [[ $name == backend ]]; then
    [[ -x $ROOT/backend/.venv/bin/uvicorn ]] || { red "backend not set up. Run './run.sh setup' first."; return 1; }
    [[ -f $ROOT/backend/.env ]] || { red "backend/.env missing. Copy backend/.env.example and add your API key."; return 1; }
    local args=(app.main:app --host "$HOST" --port "$port")
    [[ ${RELOAD:-0} == 1 ]] && args+=(--reload --reload-dir app)
    (cd "$ROOT/backend"; setsid nohup .venv/bin/uvicorn "${args[@]}" </dev/null >"$RUN/backend.log" 2>&1 & echo $! >"$RUN/backend.pid")
  else
    [[ -d $ROOT/frontend/node_modules ]] || { red "frontend not set up. Run './run.sh setup' first."; return 1; }
    (cd "$ROOT/frontend"; setsid nohup npm run dev -- --host "$HOST" --port "$port" --strictPort </dev/null >"$RUN/frontend.log" 2>&1 & echo $! >"$RUN/frontend.pid")
  fi

  printf '%s: starting… ' "$name"
  if wait_up "$name"; then
    green "up (pid $(pid_of "$name"))"
  else
    red "failed. Last log lines:"
    tail -n 15 "$RUN/$name.log"
    stop_one "$name" >/dev/null
    return 1
  fi
}

stop_one() {
  local name=$1 port pid i
  port=$(port_of "$name")
  pid=$(pid_of "$name")
  if [[ -n $pid ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  rm -f "$RUN/$name.pid"
  # Also stop copies of this project's servers started by hand in a terminal.
  for pid in $(project_listeners "$port"); do
    kill -TERM "$pid" 2>/dev/null || true
  done
  for i in $(seq 1 20); do [[ -n $(project_listeners "$port") ]] || break; sleep 0.25; done
  if port_busy "$port"; then
    red "$name: port $port is still in use by another program (pid $(lsof -t -iTCP:"$port" -sTCP:LISTEN | head -1))"
  else
    green "$name: stopped"
  fi
}

status_one() {
  local name=$1 pid port
  port=$(port_of "$name")
  pid=$(pid_of "$name")
  if [[ -n $pid ]] && curl -s -o /dev/null --max-time 2 "$(url_of "$name")"; then
    green "$name: running   pid $pid   port $port"
  elif [[ -n $pid ]]; then
    red "$name: process $pid is alive but not answering on port $port (see ./run.sh logs $name)"
  elif port_busy "$port"; then
    dim "$name: port $port in use by pid $(lsof -t -iTCP:"$port" -sTCP:LISTEN | head -1) (not started by this script)"
  else
    dim "$name: stopped"
  fi
}

setup() {
  local venv="$ROOT/backend/.venv" py="${PYTHON:-python3}"
  if [[ $EUID -eq 0 && -z ${ALLOW_ROOT:-} ]]; then
    red "Don't run setup with sudo: it leaves root-owned files that the app can't write to later."
    dim "Run it as your normal user: ./run.sh setup"
    dim "If an earlier sudo run left files behind: sudo chown -R \"\$USER\": $ROOT"
    exit 1
  fi
  if ! command -v "$py" >/dev/null; then
    red "python3 not found. Install Python 3.12 (Ubuntu/Debian: sudo apt install python3 python3-venv)."; exit 1
  fi
  if ! "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    red "Python 3.11+ is needed, found $("$py" --version 2>&1). Install 3.12 and rerun with PYTHON=python3.12 ./run.sh setup"; exit 1
  fi
  if ! command -v npm >/dev/null; then
    red "Node.js not found. Install Node 22 (https://nodejs.org or: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install nodejs)."; exit 1
  fi
  if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=12)||(a===20&&b>=19)?0:1)'; then
    red "Node 20.19+ or 22.12+ is needed, found $(node --version). Install Node 22."; exit 1
  fi

  local owned_by_root
  owned_by_root=$(find "$ROOT/.run" "$ROOT/backend" "$ROOT/frontend" -maxdepth 2 -user 0 -print -quit 2>/dev/null)
  if [[ $EUID -ne 0 && -n $owned_by_root ]]; then
    red "Some files are owned by root (e.g. $owned_by_root), probably from an earlier 'sudo ./run.sh'. Fix with:"
    dim "  sudo chown -R \"\$USER\": $ROOT"
    exit 1
  fi

  echo "backend: creating virtualenv and installing requirements…"
  # A failed earlier attempt (no python3-venv) leaves a .venv without pip; start again.
  [[ -x $venv/bin/pip ]] || rm -rf "$venv"
  [[ -d $venv ]] || "$py" -m venv "$venv" || true
  if [[ ! -x $venv/bin/pip ]]; then
    rm -rf "$venv"
    local ver; ver=$("$py" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
    red "Could not create a virtualenv with pip. On Ubuntu/Debian install the venv package, then rerun:"
    dim "  sudo apt install python3-venv python$ver-venv"
    dim "  ./run.sh setup"
    exit 1
  fi
  "$venv/bin/pip" install -q --upgrade pip
  "$venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
  [[ -f $ROOT/backend/.env ]] || { cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"; echo "created backend/.env, add your GEMINI_API_KEY"; }
  echo "frontend: installing packages…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
  green "setup done. Next: ./run.sh start"
}

targets() {
  case "${1:-all}" in
    all) echo "backend frontend" ;;
    backend|frontend) echo "$1" ;;
    *) red "unknown service '$1' (use backend or frontend)"; exit 2 ;;
  esac
}

cmd="${1:-help}"
svc="${2:-all}"
case "$cmd" in
  start)
    ok=1
    for s in $(targets "$svc"); do start_one "$s" || ok=0; done
    if [[ $ok == 1 && $svc != backend ]]; then
      echo; green "Open http://localhost:$FRONTEND_PORT"
      [[ $HOST == 0.0.0.0 ]] && dim "From another device: http://$(hostname -I | awk '{print $1}'):$FRONTEND_PORT"
    fi
    [[ $ok == 1 ]] ;;
  stop)
    for s in $(targets "$svc" | tr ' ' '\n' | tac); do stop_one "$s"; done ;;
  restart)
    for s in $(targets "$svc" | tr ' ' '\n' | tac); do stop_one "$s"; done
    for s in $(targets "$svc"); do start_one "$s"; done ;;
  status)
    for s in backend frontend; do status_one "$s"; done ;;
  logs)
    if [[ $svc == all ]]; then tail -n 30 -f "$RUN/backend.log" "$RUN/frontend.log"; else tail -n 50 -f "$RUN/$svc.log"; fi ;;
  setup)
    setup ;;
  *)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
