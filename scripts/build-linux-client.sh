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

    # Сборка релизного ZIP-пакета для Linux
    LINUX_PKG_DIR="dist/BridgeLocal-Linux-x64"
    rm -rf "${LINUX_PKG_DIR}" "dist/BridgeLocal-Linux-x64.zip"
    mkdir -p "${LINUX_PKG_DIR}/pocket" "${LINUX_PKG_DIR}/systemd"

    cp "dist/bridge-cli" "${LINUX_PKG_DIR}/"
    cp "bridge.toml" "${LINUX_PKG_DIR}/"
    if [[ -f "docs/README_LINUX.md" ]]; then
        cp "docs/README_LINUX.md" "${LINUX_PKG_DIR}/README.md"
    fi
    if [[ -d "scripts/systemd" ]]; then
        cp scripts/systemd/* "${LINUX_PKG_DIR}/systemd/"
    fi

    (cd dist && zip -r "BridgeLocal-Linux-x64.zip" "BridgeLocal-Linux-x64")
    ZIP_SIZE=$(du -h "dist/BridgeLocal-Linux-x64.zip" | cut -f1)
    echo "============================================================"
    echo "  [OK] Релизный архив собран: dist/BridgeLocal-Linux-x64.zip (${ZIP_SIZE})"
    echo "============================================================"
else
    echo "[FAIL] dist/bridge-cli не найден!"
    exit 1
fi
