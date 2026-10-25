#!/usr/bin/env bash
# Remove everything install.sh set up. Leaves Valve's own podman containers alone.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
q() { "$@" 2>&1 | grep -v 'level=warning'; }

q podman rm -f debian
q podman rmi docker.io/library/debian:testing
rm -f  "$HOME"/.local/bin/distrobox "$HOME"/.local/bin/distrobox-*
rm -f  "$HOME"/.local/share/man/man1/distrobox*.1
rm -f  "$HOME"/.local/share/bash-completion/completions/distrobox*
rm -f  "$HOME"/.local/share/zsh/site-functions/_distrobox*
rm -rf "$HOME/.local/share/icons/distrobox"
rm -f  "$HOME"/.local/share/icons/hicolor/*/apps/terminal-distrobox-icon.*
rm -f  "$HOME/.local/share/applications/debian.desktop" "$HOME/Desktop/uxplay.desktop"
echo "UxPlay and distrobox removed."
