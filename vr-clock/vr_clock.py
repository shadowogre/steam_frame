#!/usr/bin/env python3
"""A small floating clock + battery readout for the Steam Frame.

Draws a tiny panel with cairo and shows it as an OpenVR overlay that is pinned
to your head (like the Performance HUD), so it stays in the same spot in your
view in every game and on the desktop. It redraws only when the minute or the
battery changes.

Run it with the project's own Python environment (see install.sh):
    .venv/bin/python vr_clock.py --help
"""
import argparse
import ctypes
import glob
import json
import math
import os
import time

import cairo
import openvr

W, H = 360, 120  # panel size in pixels


CONFIG = os.path.expanduser("~/.config/vr-clock.json")


def to4(m):
    """HmdMatrix34_t -> 4x4 list of lists."""
    return [[m[r][c] for c in range(4)] for r in range(3)] + [[0, 0, 0, 1]]


def to34(a):
    m = openvr.HmdMatrix34_t()
    for r in range(3):
        for c in range(4):
            m[r][c] = a[r][c]
    return m


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


def head_relative(x, y, distance):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, -distance], [0, 0, 0, 1]]


def wrist_offset(up, back):
    """Panel lying flat on the back of the hand, top edge towards the fingers.

    Controller space: -z points towards the fingertips, +y is up out of the
    back of the hand, so the panel is turned to face +y and nudged back
    towards the wrist."""
    return [[1, 0, 0, 0], [0, 0, 1, up], [0, -1, 0, back], [0, 0, 0, 1]]


def save_config(**values):
    """Merge values into the saved settings file (best effort)."""
    try:
        try:
            with open(CONFIG) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        saved.update(values)
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w") as f:
            json.dump(saved, f)
    except OSError:
        pass


def hand_index(system, hand):
    """Device index of the left/right controller, or None if it isn't tracked."""
    role = (openvr.TrackedControllerRole_LeftHand if hand == "left"
            else openvr.TrackedControllerRole_RightHand)
    idx = system.getTrackedDeviceIndexForControllerRole(role)
    return None if idx == openvr.k_unTrackedDeviceIndexInvalid else idx


def facing_head(system, hand, offset, threshold):
    """True when the wrist panel is turned towards your eyes (a glance)."""
    poses = system.getDeviceToAbsoluteTrackingPose(
        openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)
    head = poses[openvr.k_unTrackedDeviceIndex_Hmd]
    ctrl = poses[hand]
    if not (head.bPoseIsValid and ctrl.bPoseIsValid):
        return False
    panel = mul(to4(ctrl.mDeviceToAbsoluteTracking), offset)
    eyes = to4(head.mDeviceToAbsoluteTracking)
    to_head = [eyes[i][3] - panel[i][3] for i in range(3)]
    dist = math.sqrt(sum(v * v for v in to_head)) or 1e-6
    return sum(panel[i][2] * to_head[i] for i in range(3)) / dist > threshold


def read_battery():
    """Return (percent, charging) from the first battery found, or (None, False)."""
    for path in sorted(glob.glob("/sys/class/power_supply/*")):
        try:
            with open(f"{path}/type") as f:
                if f.read().strip() != "Battery":
                    continue
            with open(f"{path}/capacity") as f:
                pct = int(f.read())
            with open(f"{path}/status") as f:
                charging = f.read().strip() in ("Charging", "Full")
            return pct, charging
        except (OSError, ValueError):
            continue
    return None, False


def clock_text(use_24h):
    now = time.localtime()
    if use_24h:
        return time.strftime("%H:%M", now)
    return time.strftime("%I:%M %p", now).lstrip("0")


def render(text, pct, charging):
    """Draw the panel; return it as a ctypes RGBA pixel array for OpenVR."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(surf)

    # dark rounded background so it stays readable over bright scenes
    r = 28
    c.new_sub_path()
    c.arc(W - r, r, r, -1.5708, 0)
    c.arc(W - r, H - r, r, 0, 1.5708)
    c.arc(r, H - r, r, 1.5708, 3.1416)
    c.arc(r, r, r, 3.1416, 4.7124)
    c.close_path()
    c.set_source_rgba(0.05, 0.05, 0.07, 0.78)
    c.fill()

    c.select_font_face("Noto Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    c.set_source_rgba(1, 1, 1, 1)

    if pct is None:  # no battery found: just centre the time
        c.set_font_size(58)
        ext = c.text_extents(text)
        c.move_to((W - ext.x_advance) / 2, H / 2 + ext.height / 2)
        c.show_text(text)
    else:
        c.set_font_size(44)
        c.move_to(24, H / 2 + 15)
        c.show_text(text)

        # battery icon on the right: outline, nub, and a fill sized to the charge
        bx, by, bw, bh = 272, 34, 52, 28
        low = pct <= 20 and not charging
        colour = (0.95, 0.3, 0.3) if low else (0.4, 0.9, 0.5) if charging else (1, 1, 1)
        c.set_source_rgba(*colour, 1)
        c.set_line_width(3)
        c.rectangle(bx, by, bw, bh)
        c.stroke()
        c.rectangle(bx + bw + 1, by + 8, 5, bh - 16)
        c.fill()
        c.rectangle(bx + 5, by + 5, (bw - 10) * max(0, min(100, pct)) / 100, bh - 10)
        c.fill()

        c.set_font_size(26)
        c.set_source_rgba(1, 1, 1, 1)
        label = f"{pct}%"
        ext = c.text_extents(label)
        c.move_to(bx + (bw - ext.x_advance) / 2, by + bh + 28)
        c.show_text(label)

    # cairo gives premultiplied BGRA; OpenVR wants straight RGBA
    surf.flush()
    src = bytes(surf.get_data())
    out = bytearray(len(src))
    for i in range(0, len(src), 4):
        b, g, r_, a = src[i:i + 4]
        if a:
            out[i:i + 4] = (min(255, r_ * 255 // a), min(255, g * 255 // a),
                            min(255, b * 255 // a), a)
    return (ctypes.c_ubyte * len(out)).from_buffer_copy(out)


def run_once(args):
    openvr.init(openvr.VRApplication_Overlay)
    try:
        ov = openvr.IVROverlay()
        system = openvr.IVRSystem()
        handle = ov.createOverlay("steamframe.clock", "Clock and Battery")
        ov.setOverlayWidthInMeters(handle, args.width)
        ov.setOverlayAlpha(handle, args.opacity)
        ov.setOverlaySortOrder(handle, 100)

        hmd = openvr.k_unTrackedDeviceIndex_Hmd
        wrist = args.mode == "wrist"
        if wrist:
            # rides on a controller; shown once that controller is tracked
            offset = args.saved_offset or wrist_offset(args.wrist_up, args.wrist_back)
            attached = None
            shown = False
            # pointing the other controller at it picks it up, like the head clock
            ov.setOverlayInputMethod(handle, openvr.VROverlayInputMethod_Mouse)
        else:
            # pin to the headset: x right, y up, -z forward (metres from your eyes)
            pos = head_relative(args.x, args.y, args.distance)
            ov.setOverlayTransformTrackedDeviceRelative(handle, hmd, to34(pos))
            # Let it be pointed at and picked up, but only while a menu or the
            # dashboard is open. (The "interactive if visible" flag would put laser
            # pointers on the controllers in games, replacing the game's own.)
            ov.setOverlayInputMethod(handle, openvr.VROverlayInputMethod_Mouse)
            ov.showOverlay(handle)

        last = None
        next_look = 0
        holder = None  # controller currently carrying the panel
        event = openvr.VREvent_t()
        while True:
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    return
            # pointer clicks on the overlay arrive on their own channel
            while ov.pollNextOverlayEvent(handle, event)[0]:
                if event.eventType == openvr.VREvent_MouseButtonDown and holder is None:
                    # pick up: re-express the panel's spot relative to the controller
                    holder = event.trackedDeviceIndex
                    if wrist:
                        if holder == attached:
                            holder = None  # can't carry it with the hand it's strapped to
                            continue
                        carried = mul(inv(device_pose(system, holder)),
                                      mul(device_pose(system, attached), offset))
                    else:
                        carried = mul(inv(device_pose(system, holder)),
                                      mul(device_pose(system, hmd), pos))
                    ov.setOverlayTransformTrackedDeviceRelative(handle, holder, to34(carried))
                elif event.eventType == openvr.VREvent_MouseButtonUp and holder is not None:
                    if wrist:
                        # put down: strap it back onto the wrist controller at the new spot
                        offset = mul(inv(device_pose(system, attached)),
                                     mul(device_pose(system, holder), carried))
                        ov.setOverlayTransformTrackedDeviceRelative(handle, attached, to34(offset))
                        holder = None
                        save_config(wrist_offset=[row[:] for row in offset[:3]], wrist_hand=args.hand)
                        continue
                    # put down: pin to the head again at the new spot, facing you
                    spot = mul(inv(device_pose(system, hmd)),
                               mul(device_pose(system, holder), carried))
                    pos = head_relative(spot[0][3], spot[1][3], -spot[2][3])
                    ov.setOverlayTransformTrackedDeviceRelative(handle, hmd, to34(pos))
                    holder = None
                    save_config(x=pos[0][3], y=pos[1][3], distance=-pos[2][3])
            if wrist and holder is None:
                idx = hand_index(system, args.hand)
                if idx != attached:  # controller turned on, off or swapped
                    if idx is not None:
                        ov.setOverlayTransformTrackedDeviceRelative(handle, idx, to34(offset))
                    attached = idx
                want = idx is not None and (
                    args.always or facing_head(system, idx, offset, args.glance))
                if want != shown:
                    (ov.showOverlay if want else ov.hideOverlay)(handle)
                    shown = want
            # clicks are listened for constantly, but the time and battery
            # only need a look every so often
            if time.monotonic() < next_look:
                time.sleep(0.1 if wrist else 0.05 if holder is not None else 0.25)
                continue
            next_look = time.monotonic() + args.refresh
            state = (clock_text(args.h24), *read_battery())
            if state != last:
                ov.setOverlayRaw(handle, render(*state), W, H, 4)
                last = state
    finally:
        openvr.shutdown()


def main():
    p = argparse.ArgumentParser(description="Floating clock and battery overlay for SteamVR.")
    p.add_argument("--x", type=float, default=None, help="metres right of centre (negative = left)")
    p.add_argument("--y", type=float, default=None, help="metres above centre (negative = below)")
    p.add_argument("--distance", type=float, default=None, help="metres in front of your face")
    p.add_argument("--mode", choices=("head", "wrist"), default="head",
                   help="head: pinned to your view; wrist: rides on a controller like a watch")
    p.add_argument("--hand", choices=("left", "right"), default="left", help="wrist mode: which controller")
    p.add_argument("--always", action="store_true",
                   help="wrist mode: always show it, not only when you look at your wrist")
    p.add_argument("--glance", type=float, default=0.5,
                   help="wrist mode: how squarely the wrist must face you to show (0 to 1)")
    p.add_argument("--wrist-up", type=float, default=0.05, help="wrist mode: metres above the controller")
    p.add_argument("--wrist-back", type=float, default=0.04, help="wrist mode: metres towards your elbow")
    p.add_argument("--width", type=float, default=None, help="panel width in metres (default 0.18, wrist 0.09)")
    p.add_argument("--opacity", type=float, default=0.9, help="0 to 1")
    p.add_argument("--refresh", type=float, default=5, help="seconds between time/battery checks")
    p.add_argument("--24h", dest="h24", action="store_true", help="show 24-hour time")
    args = p.parse_args()
    args.glance = min(args.glance, 0.99)  # 1 would need a perfectly square-on wrist, which never happens
    if args.width is None:
        args.width = 0.09 if args.mode == "wrist" else 0.18
    try:
        with open(CONFIG) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    args.saved_offset = None
    if args.mode == "wrist":
        m = saved.get("wrist_offset")
        # a spot saved for the other wrist would be mirrored, so start fresh
        if saved.get("wrist_hand") == args.hand and isinstance(m, list) and len(m) == 3:
            args.saved_offset = [list(map(float, r)) for r in m] + [[0, 0, 0, 1]]
    for name, fallback in (("x", -0.30), ("y", -0.22), ("distance", 1.0)):
        if getattr(args, name) is None:
            setattr(args, name, saved.get(name, fallback))

    # SteamVR may not be up yet, or may restart; keep trying quietly
    while True:
        try:
            run_once(args)
        except Exception as e:  # noqa: BLE001
            print(f"waiting for SteamVR ({e})", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
