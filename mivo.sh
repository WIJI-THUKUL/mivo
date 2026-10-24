#!/usr/bin/env bash
# MIVO CODE installer - Termux, Ubuntu/Debian (incl. proot), Alpine, Fedora, Arch, macOS.
#   bash mivo.sh        -> install / update
# Then start with:  mivo
# No "set -e": a failing step must never stop the files from being installed.

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIVO_HOME="${MIVO_HOME:-$HOME/.mivo}"
VERSION="$(grep -m1 '^VERSION' "$SRC/mivo.py" 2>/dev/null | sed 's/[^"]*"\([^"]*\)".*/\1/')"
VERSION="${VERSION:-1.0}"
BAR_W=50
LAST_TEN=-1
mkdir -p "$MIVO_HOME"
LOG="$MIVO_HOME/install.log"
: > "$LOG"
export DEBIAN_FRONTEND=noninteractive
WARNINGS=()

# ---- progress bar:  ■■■■■■■■■■■■■■■■■■■■■■■■･･････････････････････････  48%
bar() {
  local pct=$1 filled i s=""
  [ "$pct" -gt 100 ] && pct=100
  filled=$(( pct * BAR_W / 100 ))
  for ((i = 0; i < BAR_W; i++)); do
    if [ "$i" -lt "$filled" ]; then s+="■"; else s+="･"; fi
  done
  if [ -t 1 ]; then
    printf '\r\033[K\033[33m%s\033[0m %3d%%' "$s" "$pct"
  elif [ $(( pct / 10 )) -gt "$LAST_TEN" ]; then   # not a terminal: one line per 10%
    LAST_TEN=$(( pct / 10 )); printf '%s %3d%%\n' "$s" "$pct"
  fi
}

# run_step FROM TO command...  : output goes to the log, the bar creeps forward while it runs
run_step() {
  local from=$1 to=$2 p pid rc
  shift 2
  p=$from
  ( "$@" </dev/null >>"$LOG" 2>&1 ) &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    bar "$p"
    sleep 0.4
    [ "$p" -lt $(( to - 1 )) ] && p=$(( p + 1 ))
  done
  wait "$pid"; rc=$?
  bar "$to"
  return $rc
}

# root needs no sudo (proot/containers); normal users use sudo when it exists
SUDO=""
if [ "$(id -u 2>/dev/null)" != "0" ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
is_termux() { [[ "${PREFIX:-}" == *com.termux* ]] && command -v pkg >/dev/null 2>&1; }

find_python() {
  local p
  for p in python3 python; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
      command -v "$p"; return 0
    fi
  done
  return 1
}

install_python() {
  if is_termux; then
    echo "Termux: pkg install python"
    pkg install -y python && return 0
    echo "pkg failed - trying apt instead"
  fi
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-pip python3-venv && return 0
  fi
  if command -v apk >/dev/null 2>&1;    then $SUDO apk add --no-cache python3 py3-pip && return 0; fi
  if command -v dnf >/dev/null 2>&1;    then $SUDO dnf install -y python3 python3-pip && return 0; fi
  if command -v yum >/dev/null 2>&1;    then $SUDO yum install -y python3 python3-pip && return 0; fi
  if command -v pacman >/dev/null 2>&1; then $SUDO pacman -Sy --noconfirm python python-pip && return 0; fi
  if command -v zypper >/dev/null 2>&1; then $SUDO zypper -n install python3 python3-pip && return 0; fi
  if command -v brew >/dev/null 2>&1;   then brew install python && return 0; fi
  return 1
}

# Pure-Python dependencies. Ubuntu/Debian block system-wide pip (PEP 668), so outside Termux a
# private virtualenv is tried first. The python that works is written to $MIVO_HOME/.python
DEPS="requests rich prompt_toolkit"
install_deps() {
  local PYB="$1" order step
  have() { "$1" -c "import requests, rich, prompt_toolkit" >/dev/null 2>&1; }
  if have "$PYB"; then echo "$PYB" > "$MIVO_HOME/.python"; return 0; fi
  "$PYB" -m pip --version >/dev/null 2>&1 || "$PYB" -m ensurepip --upgrade
  pip_plain() { "$PYB" -m pip install --quiet $DEPS; }
  pip_force() { "$PYB" -m pip install --quiet --break-system-packages $DEPS; }
  pip_venv()  { "$PYB" -m venv "$MIVO_HOME/venv" && "$MIVO_HOME/venv/bin/python" -m pip install --quiet $DEPS \
                  && PYB="$MIVO_HOME/venv/bin/python"; }
  if is_termux; then order="pip_plain pip_force pip_venv"; else order="pip_venv pip_plain pip_force"; fi
  for step in $order; do
    if $step; then echo "$PYB" > "$MIVO_HOME/.python"; return 0; fi
  done
  return 1
}

# ============================== start ==============================
echo
printf '\033[1mInstalling mivo version: %s\033[0m\n' "$VERSION"
bar 0

# 1) Copy files FIRST so the update always lands. Bundled skills/plugins are refreshed; if you edited
#    one, your copy is kept next to it as SKILL.md.old / plugin.py.old.
mkdir -p "$MIVO_HOME/app" "$MIVO_HOME/skills" "$MIVO_HOME/plugins" "$MIVO_HOME/sessions"
if ! cp -f "$SRC/mivo.py" "$MIVO_HOME/app/mivo.py"; then
  echo; echo "Could not copy mivo.py" >&2; exit 1
fi
bar 6
if [ -d "$SRC/skills" ]; then
  for d in "$SRC"/skills/*/; do
    n="$(basename "$d")"; mkdir -p "$MIVO_HOME/skills/$n"
    t="$MIVO_HOME/skills/$n/SKILL.md"
    if [ -f "$t" ] && ! cmp -s "$d/SKILL.md" "$t"; then cp -f "$t" "$t.old"; fi
    cp -f "$d/SKILL.md" "$t"
  done
fi
bar 10
if [ -d "$SRC/plugins" ]; then
  for f in "$SRC"/plugins/*.py; do
    [ -f "$f" ] || continue
    t="$MIVO_HOME/plugins/$(basename "$f")"
    if [ -f "$t" ] && ! cmp -s "$f" "$t"; then cp -f "$t" "$t.old"; fi
    cp -f "$f" "$t"
  done
fi
bar 15

# 2) Python 3.8+
PY="$(find_python)"
bar 20
if [ -z "$PY" ]; then
  run_step 20 55 install_python
  PY="$(find_python)"
fi
if [ -z "$PY" ]; then
  echo
  echo "Python 3.8+ is required and could not be installed automatically (see $LOG). Install it, then run this script again:" >&2
  echo "  Termux:         pkg install python" >&2
  echo "  Ubuntu/Debian:  apt update && apt install -y python3 python3-pip python3-venv" >&2
  echo "  Alpine:         apk add python3 py3-pip" >&2
  echo "  Fedora:         dnf install -y python3 python3-pip" >&2
  echo "  Arch:           pacman -S python python-pip" >&2
  echo "  macOS:          brew install python" >&2
  exit 1
fi
bar 55

# 3) Dependencies
rm -f "$MIVO_HOME/.python"
run_step 55 82 install_deps "$PY" || WARNINGS+=("Could not install dependencies automatically (no internet?). Run: $PY -m pip install $DEPS")
[ -s "$MIVO_HOME/.python" ] && PY="$(cat "$MIVO_HOME/.python")"
bar 82
echo "$SRC" > "$MIVO_HOME/source"   # lets `mivo update` find this folder

# 4) Components: RTK binary (where it can run), MCP servers (Context7 by default), readiness check
run_step 82 94 env MIVO_HOME="$MIVO_HOME" "$PY" "$MIVO_HOME/app/mivo.py" setup --quiet \
  || WARNINGS+=("Component setup reported a problem (see $LOG). Run later: mivo setup")
bar 94

# 5) Global `mivo` command
if [ -n "${PREFIX:-}" ] && [ -d "$PREFIX/bin" ] && [ -w "$PREFIX/bin" ]; then BIN_DIR="$PREFIX/bin"
elif [ -d /usr/local/bin ] && [ -w /usr/local/bin ]; then BIN_DIR="/usr/local/bin"
else BIN_DIR="$HOME/.local/bin"; mkdir -p "$BIN_DIR"; fi
cat > "$BIN_DIR/mivo" <<LAUNCHER
#!/usr/bin/env bash
export MIVO_HOME="$MIVO_HOME"
exec "$PY" "$MIVO_HOME/app/mivo.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/mivo"
bar 97

# 6) Verify
INSTALLED="$("$PY" "$MIVO_HOME/app/mivo.py" --version 2>>"$LOG" | head -1)"
bar 100
echo; echo
if [ -n "$INSTALLED" ]; then
  printf '\033[32m✓ %s installed\033[0m\n' "$INSTALLED"
else
  WARNINGS+=("Installed, but the version check failed (see $LOG).")
fi
for w in "${WARNINGS[@]}"; do printf '\033[31m! %s\033[0m\n' "$w" >&2; done
echo
env MIVO_HOME="$MIVO_HOME" "$PY" "$MIVO_HOME/app/mivo.py" setup --show 2>>"$LOG"
echo
echo "Start with:  mivo        Check anytime:  mivo doctor        Update:  mivo update"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Note: add $BIN_DIR to your PATH, or run:  $BIN_DIR/mivo" ;; esac
echo "If 'mivo' cannot be executed (noexec mount), run:  $PY $MIVO_HOME/app/mivo.py"
echo "Install log: $LOG"
