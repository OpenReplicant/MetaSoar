#!/usr/bin/env bash
# Setup for a Claude Code cloud session (run by the SessionStart hook in .claude/settings.json, cloud only).
# Installs the Kaggle CLI if it is missing. The token comes from the environment's secret (KAGGLE_API_TOKEN, or
# KAGGLE_USERNAME and KAGGLE_KEY); this script never reads or writes it.
set -u
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
if ! command -v kaggle >/dev/null 2>&1; then
  python3 -m pip install --quiet --user kaggle six >/dev/null 2>&1 || python3 -m pip install --quiet --break-system-packages --user kaggle six >/dev/null 2>&1
fi
export PATH="$HOME/.local/bin:$PATH"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then echo "export PATH=\"$HOME/.local/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"; fi
if ! command -v kaggle >/dev/null 2>&1; then echo "cloud-setup: the Kaggle CLI did not install (is PyPI reachable?)"; exit 0; fi
if [ -z "${KAGGLE_API_TOKEN:-}${KAGGLE_KEY:-}" ] && [ ! -e "$HOME/.kaggle" ]; then
  echo "cloud-setup: no Kaggle token in the environment (KAGGLE_API_TOKEN, or KAGGLE_USERNAME and KAGGLE_KEY)"; exit 0
fi
if kaggle kernels list --mine --page-size 1 >/dev/null 2>&1; then echo "cloud-setup: Kaggle CLI ready";
else echo "cloud-setup: Kaggle CLI installed but the API call failed (token, or kaggle.com not allowed by the network policy)"; fi
