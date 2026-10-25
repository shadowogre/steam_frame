#!/bin/bash
# Installs aux_shortcut.py as a user service that starts before SteamVR,
# so tapping Control acts as the Steam Frame's Aux/Select button after every boot.
#
#   ./install.sh              install (or reinstall) and enable
#   ./install.sh --uninstall  stop, disable and remove
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/aux-shortcut.service"
WANTS="$UNIT_DIR/steamvr.service.wants/aux-shortcut.service"

# always talk to the main user systemd; terminals inside SteamVR's nested
# desktop point these at a different session
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

if [ "$1" = "--uninstall" ]; then
    systemctl --user stop aux-shortcut.service 2>/dev/null || true
    rm -f "$WANTS" "$UNIT"
    systemctl --user daemon-reload
    echo "Removed. Restart SteamVR to drop the pretend Aux button."
    exit 0
fi

# --- check what the shortcut needs before changing anything ---

if ! command -v python3 >/dev/null; then
    echo "Python 3 isn't installed, and this script needs it." >&2
    exit 1
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "Can't reach your user services (systemd)." >&2
    echo "Try again from the main desktop session, or after a reboot." >&2
    exit 1
fi

if [ ! -e /dev/uinput ]; then
    cat >&2 <<MSG
This device has no /dev/uinput, which lets a program act as a pretend
button. Open a terminal and type this line (it will ask for your password):

    sudo modprobe uinput

Then run ./install.sh again.
MSG
    exit 1
fi

if ! id -nG | grep -qw input; then
    cat >&2 <<MSG
Your user ($(id -un)) isn't in the "input" group, so the script wouldn't be
allowed to read the keyboard. To fix it, open a terminal and type this line
(it will ask for your password):

    sudo usermod -aG input $(id -un)

Then restart the headset and run ./install.sh again.
MSG
    exit 1
fi

mkdir -p "$UNIT_DIR/steamvr.service.wants"
cat > "$UNIT" <<EOF
[Unit]
Description=Tapping Control acts as Aux/Select button
Before=steamvr.service
StartLimitIntervalSec=60
StartLimitBurst=20

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 -u $DIR/aux_shortcut.py
# give the script a moment to create the pretend button before SteamVR looks
ExecStartPost=/usr/bin/sleep 1
StandardOutput=truncate:$DIR/log.txt
Restart=on-failure
RestartSec=2

[Install]
WantedBy=steamvr.service
EOF

# same as "systemctl --user enable", which refuses while an older
# temporary (systemd-run) copy of the service is still running
ln -sf "$UNIT" "$WANTS"
systemctl --user daemon-reload

if systemctl --user is-active --quiet aux-shortcut.service; then
    echo "Installed. Already running; it will start automatically from the next boot on."
else
    systemctl --user start aux-shortcut.service
    echo "Installed and started. Restart SteamVR once so it notices the button:"
    echo "  systemctl --user restart steamvr.service"
fi
