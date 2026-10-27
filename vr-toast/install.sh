#!/bin/bash
# Sets up vr_toast.py (popup messages in VR) and the `vrtoast` command.
#
#   ./install.sh              install (or reinstall) and start
#   ./install.sh --uninstall  stop, disable and remove the service and command
#   ./install.sh --help       list all options
set -e

usage() {
    cat <<'TEXT'
install.sh - set up VR toast popups and the `vrtoast` command

USAGE
  ./install.sh [options]      install (or reinstall) and start
  ./install.sh --uninstall    stop it and remove the service and command
  ./install.sh --help         show this page (changes nothing)

PLACING IT
  Run `vrtoast --place`. A card appears in your view:
  point a controller at it, hold the trigger, move it where you want your
  popups, and let go. The card stays 60 seconds after the command if you
  don't pick it up (and as long as you hold it), then 15 seconds after you
  let go. Card high up: popups stack downward. Low down: they stack upward.
  In between: they grow both ways. Left or right of centre: they line up
  that way. The spot is saved in ~/.config/vr-toast.json (delete that file
  to reset). The card also appears on its own the first time, until you
  have placed it once.

After installing, on this device:
  vrtoast "dinner is ready"
  vrtoast -t 15 "stays up 15 seconds"

From another computer over ssh, use the full path (ssh doesn't add
~/.local/bin to the PATH):
  ssh steamos@frame.local '~/.local/bin/vrtoast "hello"'

Options you give are saved into the service, so they apply every time
SteamVR starts. Reinstalling without options goes back to the defaults.

OPTIONS
  --vertical V      force upper (stack grows downward), lower (upward) or
                    middle (both ways). Normally you don't need this: drag
                    the placement card (see below) and it works the direction out.
  --horizontal H    force left, center or right (text lines up that way too)
  --time T          how long cards stay: a number of seconds, or quick,
                    normal (default) or long, which scale with the length
                    of the message (0.05 / 0.08 / 0.13 seconds per
                    character). `vrtoast -t ...` overrides it per message.
  --min-time S      with a speed, the shortest a card stays (default 3)
  --x N, --y N      fine-tune: extra metres right / up (negative = left / down)
  --distance N      starting distance in metres (default 1); placing the card remembers its own
  --width N         popup width in metres (default 0.40)
  --opacity N       0 to 1 (default 0.95)
  --max-visible N   cards on screen at once (default 6); extra messages wait
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
        --uninstall|--vertical|--horizontal|--time|--x|--y|--distance|--width|--opacity|--max-visible|--min-time) ;;
        -[0-9]*|[0-9]*|upper|middle|lower|left|center|right|quick|normal|long) ;;  # values
        -*) echo "Unknown option: $arg  (nothing was changed; try ./install.sh --help)"; exit 2 ;;
    esac
done

# --time takes seconds or quick/normal/long; a typo here would crash the service
prev=
for arg in "$@"; do
    if [ "$prev" = "--time" ] && ! [[ "$arg" =~ ^(quick|normal|long|[0-9]+(\.[0-9]+)?)$ ]]; then
        echo "--time takes a number of seconds, or quick, normal or long (nothing was changed)"; exit 2
    fi
    prev="$arg"
done

DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/vr-toast.service"
WANTS="$UNIT_DIR/steamvr.service.wants/vr-toast.service"
CMD="$HOME/.local/bin/vrtoast"

# always talk to the main user systemd; terminals inside SteamVR's nested
# desktop point these at a different session
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

if [ "$1" = "--uninstall" ]; then
    systemctl --user stop vr-toast.service 2>/dev/null || true
    rm -f "$WANTS" "$UNIT" "$CMD"
    systemctl --user daemon-reload
    echo "Removed. (The .venv folder is still here; delete it if you like.)"
    exit 0
fi

# --- check what it needs before changing anything ---

if [ ! -e /usr/lib/libopenvr_api.so ]; then
    echo "Can't find SteamVR's library (/usr/lib/libopenvr_api.so)." >&2
    echo "VR toasts only work on a device with SteamVR installed." >&2
    exit 1
fi

if ! python3 -c "import cairo" 2>/dev/null; then
    cat >&2 <<MSG
The popups are drawn with a free drawing library called "pycairo", and it
isn't installed on this device. (If you already set up vr-clock, it needed
the same thing.) To install it by hand, open a terminal and type these
three lines, pressing Enter after each (it will ask for your password):

    sudo steamos-readonly disable
    sudo pacman -S python-cairo
    sudo steamos-readonly enable

Then run ./install.sh again. A SteamOS update can remove packages added
this way; if the popups stop after an update, run ./install.sh again.
MSG
    exit 1
fi

# a private Python environment, so nothing touches the system Python
if [ ! -x "$DIR/.venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$DIR/.venv"
fi
if ! "$DIR/.venv/bin/python" -c "import openvr" 2>/dev/null; then
    "$DIR/.venv/bin/pip" install --quiet openvr
fi
# the pip package ships no ARM library; use the one SteamOS already has
ln -sf /usr/lib/libopenvr_api.so "$DIR"/.venv/lib/python3*/site-packages/openvr/libopenvr_api_64.so

mkdir -p "$UNIT_DIR/steamvr.service.wants" "$(dirname "$CMD")"
ln -sf "$DIR/vrtoast" "$CMD"

cat > "$UNIT" <<EOF
[Unit]
Description=VR toast popups
After=steamvr.service

[Service]
Type=simple
WorkingDirectory=$DIR
# the main desktop session's bus, so the no-VR fallback can show a normal notification
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
# add options here, e.g.  vr_toast.py --y 0.1 --max-visible 3
ExecStartPre=$DIR/wait-for-vr.sh
ExecStart=$DIR/.venv/bin/python -u $DIR/vr_toast.py $*
StandardOutput=truncate:$DIR/log.txt
TimeoutStartSec=150
Restart=always
RestartSec=3

[Install]
WantedBy=steamvr.service
EOF

ln -sf "$UNIT" "$WANTS"
systemctl --user daemon-reload
systemctl --user restart vr-toast.service
echo "Installed and running. Try:  vrtoast \"hello\""
echo "From another computer: ssh $USER@$(hostname).local '~/.local/bin/vrtoast \"hello\"'"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(Add ~/.local/bin to your PATH to use the command by name.)" ;; esac
