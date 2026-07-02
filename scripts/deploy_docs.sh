#!/usr/bin/env bash
# Publish the docs site — regenerating everything derived from code FIRST, so the site can't
# drift from the registry. Run from the repo root: scripts/deploy_docs.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> regenerating tool reference from the live registry"
.venv/Scripts/python.exe bench/dump_tools.py --json > website/app/tools/tools.generated.json

echo "==> building"
npx --prefix website next build website

echo "==> deploying to Vercel (prod)"
npx vercel --cwd website --prod
