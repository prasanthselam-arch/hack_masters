#!/usr/bin/env bash
# Control script for Health Copilot (backend + frontend).
#
#   ./run.sh start [backend|frontend]     start both (or one) in the background
#   ./run.sh stop [backend|frontend]      stop both (or one)
#   ./run.sh restart [backend|frontend]   stop, then start
#   ./run.sh status                       show what is running
#   ./run.sh logs [backend|frontend]      follow the logs
#   ./run.sh setup                        install everything: system packages (Python, Node; asks for
#                                         sudo if needed), then backend and frontend dependencies
#
# Env: HOST=0.0.0.0 to open the site from another device (e.g. a phone camera on the same Wi-Fi),
#      RELOAD=1 to auto-reload the backend on code changes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 'sudo ./run.sh start' etc. would leave root-owned servers and files; run as the real user instead.
# Only setup needs root, for the system packages, and it drops back to the user itself.
if [[ $EUID -eq 0 && -n ${SUDO_USER:-} && $SUDO_USER != root && ${1:-} != setup ]]; then
  exec sudo -u "$SUDO_USER" -H -- "$ROOT/run.sh" "$@"
fi

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
    find_node >/dev/null || { red "Node 20.19+ or 22.12+ not found. Run './run.sh setup' to install it."; return 1; }
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

# --- setup -----------------------------------------------------------------------------------------

TOOLS="$ROOT/.tools"
USER_HOME=$HOME
if [[ $EUID -eq 0 && -n ${SUDO_USER:-} ]]; then USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6); fi

as_root() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

# Python 3.11-3.13: the pinned wheels (pillow, numpy, opencv) don't exist for newer versions yet.
find_python() {
  local c
  for c in ${PYTHON:-} python3.12 python3.13 python3.11 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null && { echo "$c"; return 0; }
  done
  return 1
}
py_version() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])'; }
py_has_venv() { "$1" -c 'import ensurepip, venv' 2>/dev/null; }

# Vite needs Node 20.19+ or 22.12+. sudo resets PATH, so also look where nvm and volta keep Node,
# and in .tools/node, where setup downloads it if there is none.
node_version_ok() {
  "$1" -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=12)||(a===20&&b>=19)?0:1)' 2>/dev/null
}
find_node() {
  local n
  for n in "$(command -v node 2>/dev/null)" "$TOOLS/node/bin/node" \
           $(ls -d "$USER_HOME"/.nvm/versions/node/v*/bin/node 2>/dev/null | sort -rV) "$USER_HOME/.volta/bin/node"; do
    [[ -n $n && -x $n ]] && node_version_ok "$n" && { echo "$n"; return 0; }
  done
  return 1
}
use_node() {
  local n
  n=$(find_node) || return 1
  PATH="$(dirname "$n"):$PATH"
  export PATH
}

install_node() {
  local arch base sum file tmp
  case $(uname -m) in
    x86_64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) red "No prebuilt Node for $(uname -m). Install Node 22 yourself and rerun."; exit 1 ;;
  esac
  base=https://nodejs.org/dist/latest-v22.x
  echo "frontend: downloading Node 22 from nodejs.org into .tools/node (nothing system-wide)…"
  read -r sum file < <(curl -fsSL "$base/SHASUMS256.txt" | grep "linux-$arch.tar.gz\$" || true)
  [[ -n ${file:-} ]] || { red "Could not reach nodejs.org. Install Node 22 yourself and rerun."; exit 1; }
  tmp=$(mktemp -d)
  curl -fsSL "$base/$file" -o "$tmp/$file"
  (cd "$tmp" && echo "$sum  $file" | sha256sum -c --quiet -) || { red "Node download failed its checksum."; exit 1; }
  rm -rf "$TOOLS/node" && mkdir -p "$TOOLS/node"
  tar -xzf "$tmp/$file" -C "$TOOLS/node" --strip-components=1
  rm -rf "$tmp"
}

# Only small system packages need root. Python and Node have no-root fallbacks (uv, .tools/node),
# so apt problems such as a broken sources.list are warnings, not failures.
install_system_packages() {
  local py pkgs=()
  py=$(find_python || true)
  if [[ -n $py ]] && ! py_has_venv "$py"; then pkgs+=("python$(py_version "$py")-venv"); fi
  command -v lsof >/dev/null 2>&1 || pkgs+=(lsof)
  command -v curl >/dev/null 2>&1 || pkgs+=(curl ca-certificates)
  if [[ ${#pkgs[@]} -eq 0 ]]; then
    dim "system: ok (python ${py:+$(py_version "$py")}${py:-via uv}, lsof, curl)"
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    echo "system: installing ${pkgs[*]} (needs root)…"
    export DEBIAN_FRONTEND=noninteractive
    as_root apt-get update -qq || dim "system: apt-get update reported errors (above); trying the install anyway"
    as_root apt-get install -y -qq "${pkgs[@]}" >/dev/null || dim "system: could not install ${pkgs[*]}; continuing without"
    hash -r
  else
    dim "system: not an apt system; please install ${pkgs[*]} if setup fails"
  fi
  command -v curl >/dev/null 2>&1 || { red "curl is required. Install it (fix apt first if it showed errors) and rerun."; exit 1; }
}

# uv downloads a standalone Python into the user's home, for systems whose packages only offer
# an unsupported version (e.g. 3.14) or lack the venv module. Nothing system-wide changes.
find_uv() {
  command -v uv 2>/dev/null || { [[ -x $HOME/.local/bin/uv ]] && echo "$HOME/.local/bin/uv"; }
}
make_venv() {
  local venv=$1 py uv
  py=$(find_python || true)
  if [[ -n $py ]] && py_has_venv "$py"; then
    echo "backend: creating virtualenv with $py ($(py_version "$py"))…"
    "$py" -m venv "$venv"
    return
  fi
  uv=$(find_uv || true)
  if [[ -z $uv ]]; then
    echo "backend: no usable Python 3.11-3.13 with venv, installing uv to ~/.local/bin…"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
    uv=$(find_uv) || { red "Could not install uv. Install Python 3.12 with venv and rerun."; exit 1; }
  fi
  echo "backend: creating virtualenv with a uv-managed Python 3.12 (downloaded once)…"
  "$uv" venv --quiet --seed --python 3.12 --python-preference only-managed "$venv"
}

setup() {
  local venv="$ROOT/backend/.venv"

  install_system_packages

  # Under sudo, only the system packages above are installed as root. The project files and the rest
  # of the setup belong to the user who ran sudo, so the app can write to them later.
  if [[ $EUID -eq 0 && -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
    chown -R "$SUDO_USER": "$ROOT"
    exec sudo -u "$SUDO_USER" -H -- "$ROOT/run.sh" setup
  fi
  if [[ $EUID -ne 0 ]] && [[ -n $(find "$ROOT" -path "$ROOT/.git" -prune -o -user 0 -print -quit 2>/dev/null) ]]; then
    dim "fixing files left owned by root by an earlier sudo run (may ask for your password)"
    as_root chown -R "$(id -un)": "$ROOT"
  fi

  if ! use_node; then
    install_node
    use_node || { red "Node install failed."; exit 1; }
  fi
  dim "node: $(node --version) ($(command -v node))"

  # Rebuild a .venv left without pip by a failed attempt, or made with an unsupported Python.
  if [[ ! -x $venv/bin/pip ]] || ! "$venv/bin/python" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null; then
    rm -rf "$venv"
  fi
  [[ -d $venv ]] || make_venv "$venv"
  echo "backend: installing requirements…"
  "$venv/bin/pip" install -q --upgrade pip
  "$venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
  if [[ ! -f $ROOT/backend/.env ]]; then
    cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
    echo "created backend/.env"
  fi

  echo "frontend: installing packages…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund --loglevel=error)

  green "setup done."
  if ! grep -E '^(GEMINI|OPENAI)_API_KEY=.+' "$ROOT/backend/.env" | grep -qv 'your-'; then
    echo "Next: put your key in backend/.env (GEMINI_API_KEY=...), then ./run.sh start"
  else
    echo "Next: ./run.sh start"
  fi
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
use_node || true
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
    sed -n '2,13p' "$ROOT/run.sh" | sed 's/^# \{0,1\}//' ;;
esac
