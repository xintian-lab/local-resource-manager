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
"$PYTHON" -c "from app.ui.app_icon import ensure_build_icons; ensure_build_icons()"
ADD_DATA="$PROJECT_ROOT/assets/icons:assets/icons"

PYINSTALLER_ARGS=(
    --noconfirm
    --clean
    --windowed
    --name "$APP_NAME"
    --add-data "$ADD_DATA"
)

ICON_ICNS="$ICONS_DIR/app_icon.icns"
ICON_PNG="$ICONS_DIR/app_icon.png"
if [[ -f "$ICON_ICNS" ]]; then
    PYINSTALLER_ARGS+=(--icon "$ICON_ICNS")
elif [[ -f "$ICON_PNG" ]]; then
    PYINSTALLER_ARGS+=(--icon "$ICON_PNG")
fi

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
