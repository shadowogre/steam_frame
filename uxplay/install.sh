#!/usr/bin/env bash
# Set up UxPlay (AirPlay mirroring receiver) on the Steam Frame.
# SteamOS has no distrobox, and OS updates wipe pacman installs, so everything
# lives in $HOME: distrobox in ~/.local, UxPlay in a Debian container.
# Safe to re-run: every step skips itself if already done.
# Run as your normal user (no sudo needed on the host).
set -euo pipefail

NAME=debian
IMAGE=docker.io/library/debian:testing
DISTROBOX_VERSION=1.8.2.5   # pinned v1 shell-script release (v2 is still a release candidate)
BIN="$HOME/.local/bin"
export PATH="$BIN:$PATH"

# --- check what UxPlay needs before changing anything ---

[[ $EUID -ne 0 ]] || { echo "Run this as your normal user, not with sudo or as root." >&2; exit 1; }

if ! command -v podman >/dev/null; then
  cat >&2 <<MSG
"podman" (the program that runs the Debian container) isn't installed.
SteamOS normally comes with it, so something is unusual about this device.
UxPlay can't be set up without it.
MSG
  exit 1
fi

if ! command -v curl >/dev/null; then
  echo "\"curl\" (used to download files) isn't installed, and this script needs it." >&2
  exit 1
fi

# the downloads (distrobox, Debian, UxPlay) need a connection
if ! curl -fsS --max-time 10 -o /dev/null https://raw.githubusercontent.com 2>/dev/null; then
  cat >&2 <<MSG
Can't reach the internet. This script has to download about 150 MB, so
connect the headset to Wi-Fi, then run ./install.sh again.
MSG
  exit 1
fi

# Debian plus UxPlay need roughly 1 GB; ask for 2 GB so there's room to spare
free_kb=$(df --output=avail -k "$HOME" | tail -1)
if (( free_kb < 2 * 1024 * 1024 )); then
  echo "Not enough free space: UxPlay needs about 2 GB free and only $(( free_kb / 1024 )) MB is available." >&2
  exit 1
fi

# Podman may print a harmless "Failed to add pause process to systemd sandbox cgroup"
# warning. Don't filter it with a pipe/process substitution: the container's
# long-lived process holds the pipe open and the script then appears to hang.
dbx() { distrobox "$@"; }

echo ">> 1/4 distrobox"
if [[ ! -x "$BIN/distrobox" ]]; then
  # SteamOS doesn't include distrobox. Download the installer to a file (not
  # piped straight into sh) so it can be inspected, then install under ~/.local.
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  curl -fsSL https://raw.githubusercontent.com/89luca89/distrobox/main/install -o "$tmp/install"
  sh "$tmp/install" --prefix "$HOME/.local" --version "$DISTROBOX_VERSION"
fi

echo ">> 2/4 Debian container (first run downloads ~150 MB)"
if ! podman container exists "$NAME" 2>/dev/null; then
  # Snag: avahi's client library talks to the host's avahi over D-Bus, and a
  # container has no system bus, so UxPlay fails with "No DNS-SD Server found".
  # Mount the host's bus socket into the container at creation time.
  dbx create --yes --name "$NAME" --image "$IMAGE" \
    --volume /run/dbus/system_bus_socket:/run/dbus/system_bus_socket
fi

echo ">> 3/4 UxPlay + GStreamer plugins inside the container"
# Snags: gstreamer1.0-vaapi no longer exists in Debian testing (don't add it back);
# the container must NOT run its own avahi-daemon, it uses the host's.
# The first 'enter' finishes container setup and can be slow.
dbx enter "$NAME" -- bash -c '
  set -e
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    uxplay gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-pulseaudio
  command -v uxplay
'

echo ">> 4/4 Desktop launcher"
mkdir -p "$HOME/Desktop"
cat > "$HOME/Desktop/uxplay.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=UxPlay
GenericName=AirPlay receiver
Comment=Receive AirPlay screen mirroring (runs in the Debian container)
Exec=$BIN/distrobox enter $NAME -- uxplay
Icon=video-display
Terminal=true
Categories=AudioVideo;
DESK
chmod +x "$HOME/Desktop/uxplay.desktop"

echo
echo "Done. Start it with the UxPlay icon on the desktop, or:"
echo "  distrobox enter $NAME -- uxplay"
echo "Then pick 'frame' (or the name UxPlay shows) from Screen Mirroring on your iPhone/Mac."
