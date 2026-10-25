#!/usr/bin/env python3
"""Toast popups for the Steam Frame, shown as a floating OpenVR overlay.

Listens on a unix socket for messages from the `vrtoast` command and stacks them
as cards in front of you. A new message never replaces an old one: cards pile
up (up to --max-visible), the rest wait their turn, and each card goes away on
its own after a few seconds. If SteamVR isn't running, messages become normal
desktop notifications instead, so nothing is lost.

Run it with the project's own Python environment (see install.sh):
    .venv/bin/python vr_toast.py --help
"""
import argparse
import collections
import ctypes
import json
import math
import os
import select
import signal
import socket
import subprocess
import time

import cairo
import openvr

# not $XDG_RUNTIME_DIR: terminals inside SteamVR's nested desktop point it elsewhere
SOCK = f"/run/user/{os.getuid()}/vr-toast.sock"

W = 560           # card width in pixels
PAD = 12
LINE = 22         # line height
MAX_LINES = 8     # longest a single card gets
GAP = 8
FONT = 17
CANVAS_LINES = 20  # screen space for all cards together, in lines of text


def to34(a):
    m = openvr.HmdMatrix34_t()
    for r in range(3):
        for c in range(4):
            m[r][c] = a[r][c]
    return m


def open_socket():
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o600)
    s.setblocking(False)
    return s


def drain(sock, wait=0.0):
    """Collect messages waiting on the socket, waiting up to `wait` seconds.

    Each is {"text", "secs", "speed"} for a popup, or {"cmd": "place"}."""
    out = []
    ready = select.select([sock], [], [], wait)[0]
    while ready:
        try:
            data = sock.recv(65536)
        except BlockingIOError:
            break
        try:
            msg = json.loads(data)
            if msg.get("cmd") == "place":
                out.append({"cmd": "place"})
                continue
            text = "\n".join(" ".join(l.split()) for l in str(msg["text"]).strip().splitlines())[:600]
            if text:
                secs = msg.get("secs")
                out.append({"text": text, "secs": float(secs) if secs else None,
                            "speed": msg.get("speed")})
        except (ValueError, KeyError, TypeError):
            pass
    return out


def desktop_fallback(text):
    """No VR right now: show a plain desktop notification instead."""
    try:
        subprocess.run(["notify-send", "-a", "vrtoast", text], check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


_measure = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
_measure.select_font_face("Noto Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
_measure.set_font_size(FONT)


def wrap(text, width):
    """Split text into lines that fit `width` pixels, ending with ... if too long."""
    c = _measure
    lines = []
    for para in text.split("\n"):  # each line break in the message starts a new line
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if c.text_extents(trial).x_advance <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        last = lines[-1]
        while last and c.text_extents(last + "\u2026").x_advance > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "\u2026"
    return lines


def card_height(lines):
    return 2 * PAD + len(lines) * LINE


CANVAS_H = card_height([""] * CANVAS_LINES)


def render(cards, vertical, horizontal, canvas_h=CANVAS_H):
    """Draw the cards (each a list of lines, oldest first); return RGBA pixels for OpenVR.

    upper: stack hangs from the top, newest at the bottom.
    lower: stack sits on the bottom, newest at the top.
    middle: stack is centred, newest at the bottom."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, canvas_h)
    c = cairo.Context(surf)
    c.select_font_face("Noto Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    c.set_font_size(FONT)
    order = list(reversed(cards)) if vertical == "lower" else list(cards)
    total = sum(card_height(l) for l in order) + GAP * max(0, len(order) - 1)
    y = {"upper": 0, "middle": (canvas_h - total) / 2, "lower": canvas_h - total}[vertical]
    for lines in order:
        ch = card_height(lines)
        r = 16
        c.new_sub_path()
        c.arc(W - r, y + r, r, -1.5708, 0)
        c.arc(W - r, y + ch - r, r, 0, 1.5708)
        c.arc(r, y + ch - r, r, 1.5708, 3.1416)
        c.arc(r, y + r, r, 3.1416, 4.7124)
        c.close_path()
        c.set_source_rgba(0.05, 0.05, 0.07, 0.85)
        c.fill()
        c.set_source_rgba(1, 1, 1, 1)
        for i, line in enumerate(lines):
            adv = c.text_extents(line).x_advance
            x = {"left": PAD, "center": (W - adv) / 2, "right": W - PAD - adv}[horizontal]
            c.move_to(x, y + PAD + (i + 1) * LINE - 8)
            c.show_text(line)
        y += ch + GAP
    surf.flush()
    # cairo is BGRA, OpenVR wants RGBA. Colours aren't un-premultiplied: the
    # background is near-black and the text opaque, so only the faintest
    # antialiased edges differ.
    src = bytes(surf.get_data())
    out = bytearray(src)
    out[0::4], out[2::4] = src[2::4], src[0::4]
    return (ctypes.c_ubyte * len(out)).from_buffer_copy(out)


# Where the stack sits when --vertical / --horizontal are given: metres from
# straight ahead at 1 m. The top edge (upper), middle (middle) or bottom edge
# (lower) of the stack, and the middle of the cards across.
ANCHOR_Y = {"upper": 0.05, "middle": -0.30, "lower": -0.55}
ANCHOR_X = {"left": -0.225, "center": 0.0, "right": 0.25}

CONFIG = os.path.expanduser("~/.config/vr-toast.json")
# where you drop the placement card (metres at 1 m) picks direction and alignment:
UPPER_ABOVE = -0.12   # higher than this: stack grows downward
LOWER_BELOW = -0.42   # lower than this: stack grows upward, else both ways
SIDE = 0.12           # further than this from centre: left / right aligned
LIMIT_X, LIMIT_Y = 0.5, (-0.65, 0.35)  # keep a dropped card inside your view
LIMIT_D = (0.4, 3.0)  # nearest and farthest it can be dropped, metres
PLACE_SECS = 60       # placement card goes away after this long if you don't pick it up
PLACED_SECS = 15      # ...or this long after you drop it
PLACE_H = card_height(["", "", ""])  # placement card: three lines of text

# how long a card stays, per character of message (seconds); "-t" picks one
SPEEDS = {"quick": 0.05, "normal": 0.08, "long": 0.13}
MAX_HOLD = 60


def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(**values):
    """Merge values into the saved settings file (best effort)."""
    try:
        saved = load_config()
        saved.update(values)
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w") as f:
            json.dump(saved, f)
    except OSError:
        pass


def classify(args, x, y):
    """(vertical, horizontal) for a card dropped with its middle at x, y."""
    vertical = args.vertical or ("upper" if y > UPPER_ABOVE else "lower" if y < LOWER_BELOW else "middle")
    horizontal = args.horizontal or ("left" if x < -SIDE else "right" if x > SIDE else "center")
    return vertical, horizontal


def hold_time(args, item):
    """Seconds a message stays up: its own -t, else the service's setting."""
    if item.get("secs"):
        return item["secs"]
    if args.fixed:
        return args.fixed
    factor = SPEEDS.get(item.get("speed")) or args.factor
    return max(args.min_time, min(MAX_HOLD, factor * len(item["text"])))


def layout_for(args, hx, hy):
    """(vertical, horizontal, anchor_x, anchor_y) from the saved spot.

    Explicit --vertical / --horizontal win for their own direction."""
    vertical, horizontal = classify(args, hx, hy)
    ax = ANCHOR_X[horizontal] if args.horizontal else hx
    ay = ANCHOR_Y[vertical] if args.vertical else hy
    return vertical, horizontal, ax + args.x, ay + args.y


def head_relative(x, y, distance):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, -distance], [0, 0, 0, 1]]


def to4(m):
    """HmdMatrix34_t -> 4x4 list of lists."""
    return [[m[r][c] for c in range(4)] for r in range(3)] + [[0, 0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def inv(a):
    """Inverse of a rigid transform (rotation + translation)."""
    r = [[a[j][i] for j in range(3)] for i in range(3)]  # transpose
    t = [-sum(r[i][k] * a[k][3] for k in range(3)) for i in range(3)]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0, 0, 0, 1]]


def device_pose(system, index):
    poses = system.getDeviceToAbsoluteTrackingPose(
        openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)
    return to4(poses[index].mDeviceToAbsoluteTracking)


def run_once(args, sock):
    openvr.init(openvr.VRApplication_Overlay)
    try:
        ov = openvr.IVROverlay()
        system = openvr.IVRSystem()
        hmd = openvr.k_unTrackedDeviceIndex_Hmd
        stack = ov.createOverlay("steamframe.toast", "Toasts")
        # canvas is wider than the cards are tall, so width fixes the scale
        ov.setOverlayWidthInMeters(stack, args.width)
        ov.setOverlayAlpha(stack, args.opacity)
        ov.setOverlaySortOrder(stack, 200)
        saved = load_config()
        # how far in front of you; a card dropped closer also looks bigger
        d = max(LIMIT_D[0], min(LIMIT_D[1], float(saved.get("distance", args.distance))))
        stack_h = card_h = 0.0  # heights in "metres at 1 m", like hx, hy (set in place)

        # The placement card: grab it and drop it where you want popups. Where
        # it lands decides the stack's direction and alignment. Shown only on
        # request (`vrtoast --place`) and the first time, before a spot is saved.
        card = ov.createOverlay("steamframe.toast.place", "Toast position")
        ov.setOverlayWidthInMeters(card, args.width)
        ov.setOverlayAlpha(card, args.opacity)
        ov.setOverlaySortOrder(card, 300)
        ov.setOverlayInputMethod(card, openvr.VROverlayInputMethod_Mouse)

        # saved as metres at 1 m so it scales with the distance
        hx = max(-LIMIT_X, min(LIMIT_X, float(saved.get("x", 0.0))))
        hy = max(LIMIT_Y[0], min(LIMIT_Y[1], float(saved.get("y", 0.05))))
        layout = card_pos = None

        def place():
            """Put the stack and the placement card where the saved spot says."""
            nonlocal layout, card_pos, stack_h, card_h
            stack_h = args.width * CANVAS_H / W / d
            card_h = args.width * PLACE_H / W / d
            layout = layout_for(args, hx, hy)
            vertical, horizontal, ax, ay = layout
            # the overlay is positioned by its middle, so shift it by half its
            # height to line up the edge the stack grows from
            edge = {"upper": -stack_h / 2, "middle": 0.0, "lower": stack_h / 2}[vertical]
            ov.setOverlayTransformTrackedDeviceRelative(
                stack, hmd, to34(head_relative(ax * d, (ay + edge) * d, d)))
            edge = {"upper": -card_h / 2, "middle": 0.0, "lower": card_h / 2}[vertical]
            card_pos = head_relative(ax * d, (ay + edge) * d, d)
            ov.setOverlayTransformTrackedDeviceRelative(card, hmd, to34(card_pos))

        def draw_card():
            how = {"upper": "downward", "middle": "both ways", "lower": "upward"}[layout[0]]
            lines = ["Drag me to where you want popups",
                     f"They'll stack {how}, {layout[1]}",
                     f"I disappear {PLACED_SECS} seconds after you let go"]
            ov.setOverlayRaw(card, render([lines], layout[0], layout[1], PLACE_H), W, PLACE_H, 4)

        place()
        draw_card()

        waiting = collections.deque()  # popups not yet on screen
        showing = []                   # [lines, expires_at]
        shown_state = None
        stack_visible = False
        placing_until = time.monotonic() + PLACE_SECS if "x" not in saved else 0
        card_visible = False
        holder = None                  # controller carrying the card
        carried = None
        event = openvr.VREvent_t()
        while True:
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    system.acknowledgeQuit_Exiting()
                    return
            # pointer clicks on the card arrive on the overlay's own channel
            while ov.pollNextOverlayEvent(card, event)[0]:
                if event.eventType == openvr.VREvent_MouseButtonDown and holder is None:
                    # pick up: re-express the card's spot relative to the controller
                    holder = event.trackedDeviceIndex
                    carried = mul(inv(device_pose(system, holder)),
                                  mul(device_pose(system, hmd), card_pos))
                    ov.setOverlayTransformTrackedDeviceRelative(card, holder, to34(carried))
                elif event.eventType == openvr.VREvent_MouseButtonUp and holder is not None:
                    # put down: see where it landed in your view; that decides
                    # which way the stack grows and how it lines up
                    spot = mul(inv(device_pose(system, hmd)),
                               mul(device_pose(system, holder), carried))
                    depth = max(LIMIT_D[0], min(LIMIT_D[1], -spot[2][3]))
                    d = depth
                    cx, cy = spot[0][3] / depth, spot[1][3] / depth
                    vertical, _ = classify(args, cx, cy)
                    hx = max(-LIMIT_X, min(LIMIT_X, cx))
                    hy = max(LIMIT_Y[0], min(LIMIT_Y[1],
                             cy + {"upper": 1, "middle": 0, "lower": -1}[vertical]
                             * args.width * PLACE_H / W / d / 2))
                    holder = None
                    place()
                    draw_card()
                    save_config(x=hx, y=hy, distance=d)
                    placing_until = time.monotonic() + PLACED_SECS
                    shown_state = None
            waiting_msgs = drain(sock, 0.03 if holder is not None else 0.1)
            now = time.monotonic()
            for item in waiting_msgs:
                if item.get("cmd") == "place":
                    placing_until = now + PLACE_SECS
                else:
                    waiting.append(item)
            placing = holder is not None or now < placing_until
            if placing != card_visible:
                (ov.showOverlay if placing else ov.hideOverlay)(card)
                card_visible = placing
            showing[:] = [t for t in showing if t[1] > now]
            # a free slot lets the next waiting message in
            # (a tall card makes the ones behind it wait until there's room)
            while waiting and len(showing) < args.max_visible:
                item = waiting[0]
                lines = wrap(item["text"], W - 2 * PAD)
                used = sum(card_height(t[0]) + GAP for t in showing)
                if showing and used + card_height(lines) > CANVAS_H:
                    break
                waiting.popleft()
                showing.append([lines, now + hold_time(args, item)])
            state = (tuple(tuple(t[0]) for t in showing), layout)
            if state != shown_state:
                if showing:
                    ov.setOverlayRaw(stack, render([t[0] for t in showing], layout[0], layout[1]),
                                     W, CANVAS_H, 4)
                    if not stack_visible:
                        ov.showOverlay(stack)
                        stack_visible = True
                elif stack_visible:
                    ov.hideOverlay(stack)
                    stack_visible = False
                shown_state = state
    finally:
        openvr.shutdown()


def main():
    p = argparse.ArgumentParser(description="VR toast popups, fed by the `vrtoast` command.")
    p.add_argument("--vertical", choices=("upper", "middle", "lower"), default=None,
                   help="force a direction: upper grows downward, lower upward, middle both ways "
                        "(default: worked out from where you drop the placement card)")
    p.add_argument("--horizontal", choices=("left", "center", "right"), default=None,
                   help="force left / center / right placement and text alignment "
                        "(default: worked out from the placement card)")
    p.add_argument("--x", type=float, default=0.0, help="fine-tune: extra metres to the right")
    p.add_argument("--y", type=float, default=0.0, help="fine-tune: extra metres up (negative = down)")
    p.add_argument("--distance", type=float, default=1.0, help="metres in front of your face")
    p.add_argument("--width", type=float, default=0.40, help="popup width in metres")
    p.add_argument("--opacity", type=float, default=0.95, help="0 to 1")
    p.add_argument("--max-visible", type=int, default=6, help="cards on screen at once")
    p.add_argument("--time", default="normal", metavar="SECONDS|quick|normal|long",
                   help="how long cards stay: exact seconds, or a speed that scales with message "
                        "length (quick 0.05, normal 0.08, long 0.13 seconds per character)")
    p.add_argument("--min-time", type=float, default=3, help="with a speed, the shortest a card stays, seconds")
    args = p.parse_args()
    args.fixed, args.factor = None, SPEEDS["normal"]
    if args.time in SPEEDS:
        args.factor = SPEEDS[args.time]
    else:
        try:
            args.fixed = float(args.time)
        except ValueError:
            p.error("--time takes a number of seconds, or quick, normal or long")
    args.max_visible = max(1, args.max_visible)

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    sock = open_socket()
    # SteamVR may not be up yet, or may restart; meanwhile use desktop popups
    while True:
        try:
            run_once(args, sock)
        except Exception as e:  # noqa: BLE001
            print(f"waiting for SteamVR ({e})", flush=True)
        end = time.monotonic() + 3
        while time.monotonic() < end:
            for item in drain(sock, 0.5):
                desktop_fallback(item.get("text") or "Position mode needs SteamVR to be running")


if __name__ == "__main__":
    main()
