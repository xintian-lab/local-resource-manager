#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

APP_NAME="Local Resource Manager"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
PYTHON="$VENV_PYTHON"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

echo "Building ${APP_NAME}.app..."
echo "Using Python: $PYTHON"

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller not found. Installing project requirements..."
    "$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
fi

rm -rf "$PROJECT_ROOT/build"
rm -f "$PROJECT_ROOT/${APP_NAME}.spec"

ICONS_DIR="$PROJECT_ROOT/assets/icons"
ICON_FILE="$("$PYTHON" -c "from app.ui.app_icon import ensure_build_icons; p = ensure_build_icons(); print(p or '')")"
if [[ -z "$ICON_FILE" || ! -f "$ICON_FILE" ]]; then
    echo "Failed to generate app_icon.icns (macOS requires .icns for PyInstaller)." >&2
    exit 1
fi
if [[ "$ICON_FILE" != *.icns ]]; then
    echo "Expected .icns icon for macOS build, got: $ICON_FILE" >&2
    exit 1
fi

ADD_DATA="$PROJECT_ROOT/assets/icons:assets/icons"

PYINSTALLER_ARGS=(
    --noconfirm
    --clean
    --windowed
    --name "$APP_NAME"
    --add-data "$ADD_DATA"
    --icon "$ICON_FILE"
)

"$PYTHON" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$PROJECT_ROOT/main.py"

APP_PATH="$PROJECT_ROOT/dist/${APP_NAME}.app"
echo ""
echo "Build complete:"
echo "$APP_PATH"
echo ""
echo "Run it with:"
echo "open \"$APP_PATH\""
echo ""
echo "Zip for GitHub Release (from project root):"
echo "ditto -c -k --keepParent \"dist/${APP_NAME}.app\" \"dist/Local-Resource-Manager-macOS.zip\""
