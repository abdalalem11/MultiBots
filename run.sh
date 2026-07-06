#!/usr/bin/env bash
# run.sh — clone bot repos and install their requirements.
#
# Enterprise improvements over the original:
#   * Each clone is retried up to 3 times with backoff (transient network).
#   * Missing requirements.txt in a bot repo is a warning, not fatal.
#   * Idempotent: if a bot dir already exists, skip the clone (faster rebuilds).
#   * Uses `set -euo pipefail` so failures bubble up to the Docker build.
#   * All output is tagged with the bot name for easy debugging.
#
# Exit codes:
#   0  — all bots cloned (or already present) successfully
#   1+ — at least one bot failed to clone after retries

set -euo pipefail

CONFIG_FILE="${1:-config.json}"
MAX_RETRIES=3
RETRY_DELAY=5

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "FATAL: config file '$CONFIG_FILE' not found." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "FATAL: jq is required but not installed." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "FATAL: git is required but not installed." >&2
  exit 1
fi

# Pull the list of (name, source) pairs from config.json.
# Note: keys starting with _ (like _dashboard, _global) are skipped.
mapfile -t ENTRIES < <(jq -r '
  to_entries[]
  | select(.key | startswith("_") | not)
  | "\(.key)\t\(.value.source // "")"
' "$CONFIG_FILE")

if [[ ${#ENTRIES[@]} -eq 0 ]]; then
  echo "WARN: no bot entries found in $CONFIG_FILE"
  exit 0
fi

failures=0

for entry in "${ENTRIES[@]}"; do
  # Split on tab — names cannot contain tabs, URLs cannot contain unencoded tabs.
  name="${entry%%$'\t'*}"
  source="${entry#*$'\t'}"

  if [[ -z "$name" || -z "$source" ]]; then
    echo "WARN: skipping malformed entry: name='$name' source='$source'" >&2
    failures=$((failures + 1))
    continue
  fi

  target_dir="$name"

  if [[ -d "$target_dir/.git" ]]; then
    echo "[$name] already cloned, pulling latest..."
    if ! (cd "$target_dir" && git pull --ff-only --quiet 2>/dev/null); then
      echo "[$name] WARN: git pull failed, continuing with existing checkout." >&2
    fi
  else
    success=0
    for attempt in $(seq 1 "$MAX_RETRIES"); do
      echo "[$name] cloning (attempt $attempt/$MAX_RETRIES)..."
      # Suppress the URL echo to avoid leaking embedded tokens in build logs.
      if git clone --quiet "$source" "$target_dir" 2>/dev/null; then
        success=1
        break
      fi
      echo "[$name] clone failed, retrying in ${RETRY_DELAY}s..." >&2
      sleep "$RETRY_DELAY"
    done
    if [[ $success -eq 0 ]]; then
      echo "[$name] FATAL: clone failed after $MAX_RETRIES attempts." >&2
      failures=$((failures + 1))
      continue
    fi
  fi

  if [[ -f "$target_dir/requirements.txt" ]]; then
    echo "[$name] installing requirements..."
    if ! pip install --no-cache-dir -r "$target_dir/requirements.txt" >/dev/null 2>&1; then
      echo "[$name] WARN: pip install failed for requirements.txt" >&2
      # Don't count as a fatal failure — some bots may still run with system deps.
    fi
  else
    echo "[$name] WARN: no requirements.txt found, skipping pip install." >&2
  fi
done

if [[ $failures -gt 0 ]]; then
  echo "FATAL: $failures bot(s) failed to clone." >&2
  exit 1
fi

echo "All bots cloned successfully."
exit 0
