#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

python -m app.download_source \
  --source-id oge-individual-disclosures \
  --use-public-sample \
  --access-acknowledged
