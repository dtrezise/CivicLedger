#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PRODUCTION_BASE_URL:-}" && -z "${CIVICLEDGER_PRODUCTION_URL:-}" ]]; then
  printf '%s\n' 'Set PRODUCTION_BASE_URL or CIVICLEDGER_PRODUCTION_URL before running production browser smoke.' >&2
  exit 2
fi

export LIVE_PRODUCTION_SMOKE=1
export PRODUCTION_BASE_URL="${PRODUCTION_BASE_URL:-${CIVICLEDGER_PRODUCTION_URL}}"

NODE_BIN="${CODEX_NODE:-$(command -v node || true)}"
if [[ -z "$NODE_BIN" ]]; then
  NODE_BIN="/Users/dan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
fi

cd "$(dirname "${BASH_SOURCE[0]}")/../frontend"
exec "$NODE_BIN" \
  node_modules/@playwright/test/cli.js test tests/pages/production-browser-smoke.spec.ts --project=mobile-chromium "$@"
