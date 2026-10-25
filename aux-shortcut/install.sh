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

if ! id -nG | grep -qw input; then
    echo "Warning: $(id -un) is not in the 'input' group; the script won't be able to read the keyboard." >&2
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
