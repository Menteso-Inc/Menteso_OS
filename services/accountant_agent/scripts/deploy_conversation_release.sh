#!/usr/bin/env bash
set -euo pipefail

app=/home/menteso_os/agents/accountant_agent
backup=/home/menteso_os/backups/accountant-agent-before-conversation-20260826
mkdir -p "$backup"
tar -czf "$backup/code.tgz" -C "$app" src scripts tests .env.example requirements.txt docs
tar -xzf /tmp/accountant-agent-update.tgz -C "$app"
chown -R menteso_os:menteso_os \
  "$app/src" "$app/scripts" "$app/tests" "$app/docs" \
  "$app/.env.example" "$app/requirements.txt"
sudo -u menteso_os bash -lc "cd '$app' && .venv/bin/python -m pytest -q"
