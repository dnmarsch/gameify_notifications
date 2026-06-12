#!/usr/bin/env bash
# Install the CoD Overlay tray-purge GNOME extension for the current user.
set -euo pipefail
UUID="cod-tray-purge@cod.local"
SRC="$(cd "$(dirname "$0")" && pwd)/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"
echo "Installed: $DEST"
echo
echo "Next:"
echo "  1) Reload GNOME Shell:  Alt+F2, type 'r', Enter   (X11)   |   log out/in (Wayland)"
echo "  2) Enable:              gnome-extensions enable $UUID"
echo "  3) Verify:              gnome-extensions info $UUID   (State: ENABLED)"
