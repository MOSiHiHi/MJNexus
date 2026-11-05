#!/usr/bin/env bash
# Reinstall local tools after the cloud container is recycled (installs outside the repo do not persist).
# - ~/.whisper-venv : faster-whisper for local speech-to-text (CPU)
# - ~/.agent-reach-venv : agent-reach CLI (installed from a git clone; GitHub archive downloads are blocked here)
set -euo pipefail

if [ ! -x "$HOME/.whisper-venv/bin/python" ]; then
  python3 -m venv "$HOME/.whisper-venv"
  "$HOME/.whisper-venv/bin/pip" install -q --upgrade pip
  "$HOME/.whisper-venv/bin/pip" install -q faster-whisper
fi

if [ ! -x "$HOME/.agent-reach-venv/bin/agent-reach" ]; then
  python3 -m venv "$HOME/.agent-reach-venv"
  "$HOME/.agent-reach-venv/bin/pip" install -q --upgrade pip
  mkdir -p /home/user/panniantong
  if [ ! -d /home/user/panniantong/agent-reach/.git ]; then
    GIT_LFS_SKIP_SMUDGE=1 git clone -q --depth 1 https://github.com/Panniantong/agent-reach /home/user/panniantong/agent-reach
  fi
  "$HOME/.agent-reach-venv/bin/pip" install -q /home/user/panniantong/agent-reach
fi

command -v ffmpeg >/dev/null || echo "ffmpeg missing: video frames and audio decoding need it" >&2
echo "ready: whisper=$HOME/.whisper-venv/bin/python agent-reach=$HOME/.agent-reach-venv/bin/agent-reach"
