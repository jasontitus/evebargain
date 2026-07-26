#!/usr/bin/env bash
# Install the EVE Bargain desktop launcher for the current user.
#
# Writes to ~/.local/share so it needs no root, and bakes this checkout's
# absolute path into the .desktop Exec lines -- desktop entries don't expand
# variables or relative paths.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"

mkdir -p "$APPS" "$ICONS/256x256/apps" "$ICONS/scalable/apps"

chmod +x "$REPO/scripts/evebargain"

sed "s|__REPO__|$REPO|g" "$REPO/scripts/evebargain.desktop" \
    > "$APPS/evebargain.desktop"
chmod +x "$APPS/evebargain.desktop"

cp "$REPO/frontend/public/notification-icon.png" "$ICONS/256x256/apps/evebargain.png"
cp "$REPO/frontend/public/favicon.svg" "$ICONS/scalable/apps/evebargain.svg"

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPS" >/dev/null 2>&1 || true

echo "Installed:"
echo "  $APPS/evebargain.desktop"
echo "  $ICONS/256x256/apps/evebargain.png"
echo
echo "Find 'EVE Bargain' in the Mint menu. Right-click it for Stop / View Logs,"
echo "or drag it to the panel or desktop to pin it."
