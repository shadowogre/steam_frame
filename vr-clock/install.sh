#!/bin/bash
# Sets up vr_clock.py (floating clock + battery overlay) and starts it with SteamVR.
#
#   ./install.sh              install (or reinstall) and enable
#   ./install.sh --uninstall  stop, disable and remove the service
#   ./install.sh --help       list all options
set -e

usage() {
    cat <<'TEXT'
install.sh - set up the floating clock + battery overlay for SteamVR

USAGE
  ./install.sh [options]      install (or reinstall) and start the clock
  ./install.sh --uninstall    stop it and remove the service
  ./install.sh --help         show this page (changes nothing)

Installing restarts the clock and can disturb SteamVR, so don't run it
from inside the headset unless you mean to. Any options you give are saved
into the service, so they apply every time SteamVR starts. Reinstalling
without options goes back to the defaults (clock pinned to your view).

OPTIONS
  --mode head|wrist   head: pinned in your view (default)
                      wrist: rides on a controller like a watch
  --hand left|right   wrist mode: which wrist (default left). Switching
                      wrists forgets the saved position.
  --always            wrist mode: always show it, not only when you look at
                      your wrist
  --glance N          wrist mode: how squarely the wrist must face you to
                      show, 0 to 1 (default 0.5)
  --opacity N         0 to 1 (default 0.9)
  --refresh S         seconds between time/battery checks (default 5)
  --24h               show 24-hour time

EXAMPLES
  ./install.sh                              clock pinned in your view
  ./install.sh --mode wrist                 watch on your left wrist
  ./install.sh --mode wrist --hand right --always

MOVING IT
  Open the SteamVR dashboard, point a controller at the clock and hold the
  trigger to carry it; let go to drop it. In wrist mode, use the controller
  that is NOT wearing it. The spot is saved in ~/.config/vr-clock.json
  (delete that file to reset).
TEXT
}

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
    esac
done

# refuse unknown options now rather than installing a service that crashes
for arg in "$@"; do
    case "$arg" in
        --uninstall|--mode|--hand|--always|--glance|--opacity|--refresh|--24h) ;;
        -*) echo "Unknown option: $arg  (nothing was changed; try ./install.sh --help)"; exit 2 ;;
    esac
done

DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/vr-clock.service"
WANTS="$UNIT_DIR/steamvr.service.wants/vr-clock.service"

# always talk to the main user systemd; terminals inside SteamVR's nested
# desktop point these at a different session
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

if [ "$1" = "--uninstall" ]; then
    systemctl --user stop vr-clock.service 2>/dev/null || true
    rm -f "$WANTS" "$UNIT"
    systemctl --user daemon-reload
    echo "Removed. (The .venv folder is still here; delete it if you like.)"
    exit 0
fi

# --- check what the clock needs before changing anything ---

if [ ! -e /usr/lib/libopenvr_api.so ]; then
    echo "Can't find SteamVR's library (/usr/lib/libopenvr_api.so)." >&2
    echo "The clock only works on a device with SteamVR installed." >&2
    exit 1
fi

# a private Python environment, so nothing touches the system Python
make_venv() {
    if [ ! -x "$DIR/.venv/bin/python" ]; then
        python3 -m venv --system-site-packages "$DIR/.venv"
    fi
}

# true if the drawing library is missing for the given python
cairo_missing() { ! "$1" -c "import cairo" 2>/dev/null; }

if cairo_missing python3; then
    cat <<MSG
The clock draws its panel with a free drawing library called "pycairo",
and it isn't installed on this device.

I can try to install it for you. It only goes inside the vr-clock folder;
nothing else on your system changes. This doesn't always work on SteamOS.
If it doesn't, I'll show you how to do it by hand.

MSG
    answer=n
    if [ -t 0 ]; then
        read -r -p "Try to install it now? [y/N] " answer
    fi
    if [[ "$answer" =~ ^[Yy] ]]; then
        make_venv
        "$DIR/.venv/bin/pip" install --quiet pycairo || true
    fi
    if cairo_missing "$DIR/.venv/bin/python"; then
        cat >&2 <<MSG

pycairo is still missing. To install it by hand, open a terminal and type
these three lines, pressing Enter after each (it will ask for your password):

    sudo steamos-readonly disable
    sudo pacman -S python-cairo
    sudo steamos-readonly enable

Then run ./install.sh again. A SteamOS update can remove packages added
this way; if the clock disappears after an update, run ./install.sh again.
MSG
        exit 1
    fi
fi

make_venv
if ! "$DIR/.venv/bin/python" -c "import openvr" 2>/dev/null; then
    "$DIR/.venv/bin/pip" install --quiet openvr
fi
# the pip package ships no ARM library; use the one SteamOS already has
ln -sf /usr/lib/libopenvr_api.so "$DIR"/.venv/lib/python3*/site-packages/openvr/libopenvr_api_64.so

mkdir -p "$UNIT_DIR/steamvr.service.wants"
cat > "$UNIT" <<EOF
[Unit]
Description=Floating clock and battery overlay
After=steamvr.service

[Service]
Type=simple
WorkingDirectory=$DIR
# add options here, e.g.  vr_clock.py --24h --x -0.25
ExecStart=$DIR/.venv/bin/python -u $DIR/vr_clock.py $*
StandardOutput=truncate:$DIR/log.txt
Restart=always
RestartSec=3

[Install]
WantedBy=steamvr.service
EOF

ln -sf "$UNIT" "$WANTS"
systemctl --user daemon-reload
systemctl --user restart vr-clock.service
echo "Installed and running. It will start with SteamVR from now on."
