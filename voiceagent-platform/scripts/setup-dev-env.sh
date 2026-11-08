#!/usr/bin/env bash
# One-shot local dev environment bootstrap.
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill in real values before running services."
fi

echo "Installing Python service dependencies..."
for d in services/telephony-gateway services/voice-pipeline services/agent-core; do
  (cd "$d" && pip install -e ".[dev]" --break-system-packages)
done

echo "Installing Node service dependencies..."
for d in services/orchestration-api services/admin-dashboard; do
  (cd "$d" && npm install)
done

echo "Setup complete. Run 'make up' to start the full local stack."
