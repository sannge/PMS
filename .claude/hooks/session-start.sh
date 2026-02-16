#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# ── Python backend dependencies ──
echo "Installing Python backend dependencies..."
# python-magic-bin may not have wheels for all platforms; swap it for python-magic
sed 's/python-magic-bin/python-magic/' "$PROJECT_DIR/fastapi-backend/requirements.txt" \
  | pip install -r /dev/stdin --quiet

# Install ruff linter
pip install ruff --quiet

# ── Node.js frontend dependencies ──
echo "Installing Node.js frontend dependencies..."
cd "$PROJECT_DIR/electron-app"
npm install

echo "Session start hook completed successfully."
