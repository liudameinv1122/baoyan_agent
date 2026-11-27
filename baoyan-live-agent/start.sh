#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  printf '%s\n' '请先安装 Python 3.11 或以上版本。'
  exit 1
fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  printf '%s\n' '请先安装 FFmpeg 和 FFprobe，具体命令见 README。'
  exit 1
fi
if [[ ! -f ui/dist/index.html ]]; then
  if ! command -v npm >/dev/null; then
    printf '%s\n' '请先安装 Node.js 22.12 或以上版本，以构建前端。'
    exit 1
  fi
  npm ci --prefix ui --no-audit --no-fund
  npm run build --prefix ui
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, PIL, dotenv, multipart' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${AGENT_PORT:-8000}" --workers 1
