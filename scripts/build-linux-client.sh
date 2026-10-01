#!/usr/bin/env bash
# ==============================================================================
# build-linux-client.sh — Сборка автономного исполняемого файла bridge-cli
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "============================================================"
echo "  Сборка автономного клиента Bridge Local (Linux x64)"
echo "============================================================"

# Сборка wheel и бинарника
LD_PRELOAD="" uv build
LD_PRELOAD="" uv run --with pyinstaller pyinstaller --clean bridge-cli.spec

if [[ -f "dist/bridge-cli" ]]; then
    chmod +x "dist/bridge-cli"
    SIZE=$(du -h "dist/bridge-cli" | cut -f1)
    echo "============================================================"
    echo "  [OK] Бинарник успешно собран: dist/bridge-cli (${SIZE})"
    echo "============================================================"
else
    echo "[FAIL] dist/bridge-cli не найден!"
    exit 1
fi
