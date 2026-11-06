#!/usr/bin/env bash
# Universal harness for macOS / Linux
set -e
cd "$(dirname "$0")"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
err(){ printf "\033[1;31m✖ %s\033[0m\n" "$*"; }
OS="$(uname -s)"

# 1) Python 3.9+
PY=""; for c in python3 python; do command -v $c >/dev/null 2>&1 && $c -c 'import sys;sys.exit(sys.version_info<(3,9))' 2>/dev/null && PY=$c && break; done
if [ -z "$PY" ]; then err "Python 3.9+ not found."; [ "$OS" = Darwin ] && echo "  brew install python python-tk" || echo "  sudo apt install python3 python3-venv python3-tk"; exit 1; fi
say "Python: $($PY --version)"

# 2) Tkinter
if ! $PY -c 'import tkinter' 2>/dev/null; then
  err "Tkinter is not available."
  if [ "$OS" = Darwin ]; then echo "  brew install python-tk"; else echo "  sudo apt install python3-tk   |  sudo dnf install python3-tkinter  |  sudo pacman -S tk"; fi
  exit 1
fi

# 3) ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  err "ffmpeg is not installed."
  if   [ "$OS" = Darwin ] && command -v brew >/dev/null; then CMD="brew install ffmpeg"
  elif command -v apt-get >/dev/null; then CMD="sudo apt-get update && sudo apt-get install -y ffmpeg"
  elif command -v dnf >/dev/null;     then CMD="sudo dnf install -y ffmpeg"
  elif command -v pacman >/dev/null;  then CMD="sudo pacman -S --noconfirm ffmpeg"
  else CMD=""; fi
  if [ -n "$CMD" ]; then
    read -r -p "Install now with: $CMD ? [y/N] " a
    if [[ "$a" =~ ^[sSyY] ]]; then eval "$CMD"; else err "ffmpeg is required."; exit 1; fi
  else err "Install it manually: https://ffmpeg.org/download.html"; exit 1; fi
fi
say "ffmpeg OK"

# 4) venv + dependencies
if [ ! -d .venv ]; then say "Creating virtual environment…"; $PY -m venv .venv; fi
. .venv/bin/activate
if [ ! -f .venv/.deps_ok ] || [ requirements.txt -nt .venv/.deps_ok ]; then
  say "Installing dependencies…"; python -m pip install -q --upgrade pip; python -m pip install -q -r requirements.txt; touch .venv/.deps_ok
fi

# 5) .env
[ -f .env ] || { cp .env.example .env; err ".env created from .env.example: add your API keys."; }

say "Starting…"
exec python app.py
