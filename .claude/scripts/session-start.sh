#!/bin/bash
set -e

# Only run in remote (Claude Code on the web) environments
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

echo "Setting up Claude Code remote environment..."

# Install dependencies
uv sync --all-extras

# Persist Python path for subsequent commands
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "PATH=/workspace/.venv/bin:\$PATH" >> "$CLAUDE_ENV_FILE"
fi

echo "Environment ready!"
