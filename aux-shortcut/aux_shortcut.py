#!/usr/bin/env python3
"""Use Control on any keyboard as the Steam Frame's Aux (Select) button.

  tap Control by itself    -> click
  hold Control by itself   -> hold the button (drag), released with Control
  Control + another key    -> normal shortcut (Ctrl+C etc.)

Keyboards are grabbed and passed through a virtual keyboard, so a Control press is
held back until it's clear which of these was meant: the desktop never sees a
Ctrl-click or Ctrl-drag."""
import ctypes, fcntl, os, select, struct, sys, time

EV_SYN, EV_KEY, EV_LED = 0, 1, 17
KEY_SPACE, KEY_LEFTCTRL, KEY_RIGHTCTRL, KEY_SELECT = 57, 29, 97, 353
HOLD_DELAY = 0.3  # seconds Control must be held alone before it starts a drag
EVENT = struct.Struct("llHHi")  # struct input_event on 64-bit
FAKE_NAME = sys.argv[1] if len(sys.argv) > 1 else "gpio-keys"
KBD_NAME = "aux-shortcut keyboard"
ONLY = os.environ.get("AUX_ONLY_KEYBOARD")  # if set, only use the keyboard with this name

def _iow(nr, size, t="U"): return (1 << 30) | (size << 16) | (ord(t) << 8) | nr
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_LEDBIT = _iow(100, 4), _iow(101, 4), _iow(105, 4)
UI_DEV_SETUP = _iow(3, 92)
UI_SET_PHYS = _iow(108, 8)
UI_DEV_CREATE, UI_DEV_DESTROY = (ord("U") << 8) | 1, (ord("U") << 8) | 2
EVIOCGRAB = _iow(0x90, 4, "E")

def make_device(name, keys, phys=None, leds=()):
    fd = os.open("/dev/uinput", os.O_RDWR | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for k in keys:
        fcntl.ioctl(fd, UI_SET_KEYBIT, k)
    if leds:
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_LED)
        for l in leds:
            fcntl.ioctl(fd, UI_SET_LEDBIT, l)
    setup = struct.pack("HHHH80sI", 0x19, 0x1, 0x1, 0x100, name.encode(), 0)
    fcntl.ioctl(fd, UI_DEV_SETUP, setup)
    if phys:  # fcntl.ioctl can't pass a pointer here, so call libc directly
        buf = ctypes.create_string_buffer(phys.encode())
        if ctypes.CDLL(None, use_errno=True).ioctl(fd, ctypes.c_ulong(UI_SET_PHYS), buf) < 0:
            raise OSError(ctypes.get_errno(), "UI_SET_PHYS failed")
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd

def emit(fd, type_, code, value):
    os.write(fd, EVENT.pack(0, 0, type_, code, value) + EVENT.pack(0, 0, EV_SYN, 0, 0))

def keyboards():
    """Event devices that have a space key (i.e. real keyboards)."""
    found = []
    for line in open("/proc/bus/input/devices").read().split("\n\n"):
        if "kbd" not in line or "uinput" in line or KBD_NAME in line:
            continue
        if ONLY and f'Name="{ONLY}"' not in line:  # testing: leave real keyboards alone
            continue
        handler = next((w for w in line.split() if w.startswith("event")), None)
        keys = next((l.split("=", 1)[1] for l in line.splitlines() if l.startswith("B: KEY=")), "")
        words = keys.split()
        if handler and words and int(words[-1], 16) & (1 << KEY_SPACE):
            found.append("/dev/input/" + handler)
    return found

def main():
    fake = make_device(FAKE_NAME, [KEY_SELECT], phys="gpio-keys/input0")  # matches the real Aux button
    # every key except mouse/gamepad buttons, so it's only seen as a keyboard, not a controller
    kbd = make_device(KBD_NAME, [*range(1, 0x100), *range(0x160, 0x220), *range(0x230, 0x2c0)], leds=range(5))
    time.sleep(0.5)  # let listeners notice the new devices
    print(f"fake Aux button '{FAKE_NAME}' and '{KBD_NAME}' ready", flush=True)

    def press_select(value):
        emit(fake, EV_KEY, KEY_SELECT, value)

    held, fds = set(), {}  # keys currently down (other than a held-back Control)
    ctrl, ctrl_since, state = None, 0.0, None  # state: None, "pending" (held back) or "drag"

    def flush_ctrl():
        """Control turned out to be part of a shortcut: pass it on after all."""
        nonlocal ctrl, state
        if state == "drag":
            press_select(0)
        emit(kbd, EV_KEY, ctrl, 1)
        held.add(ctrl)
        ctrl, state = None, None

    try:
        while True:
            for path in keyboards():  # pick up keyboards that (re)connect
                if path not in fds.values():
                    try:
                        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
                        fcntl.ioctl(fd, EVIOCGRAB, 1)
                        fds[fd] = path
                        print("watching", path, flush=True)
                    except OSError:
                        pass
            timeout = 2.0
            if state == "pending":
                timeout = max(0.0, ctrl_since + HOLD_DELAY - time.monotonic())
            ready, _, _ = select.select([kbd, *fds], [], [], timeout)
            if state == "pending" and time.monotonic() - ctrl_since >= HOLD_DELAY:
                state = "drag"
                press_select(1)
                print("hold", flush=True)
            for fd in ready:
                try:
                    data = os.read(fd, EVENT.size * 64)
                except OSError:  # keyboard disconnected
                    if fd == kbd:
                        continue
                    os.close(fd); fds.pop(fd)
                    if state == "drag":
                        press_select(0)
                    ctrl, state = None, None
                    continue
                for i in range(0, len(data), EVENT.size):
                    _, _, type_, code, value = EVENT.unpack_from(data, i)
                    if fd == kbd:  # desktop set Caps Lock etc.: light up the real keyboards
                        if type_ == EV_LED:
                            for real in fds:
                                try: emit(real, EV_LED, code, value)
                                except OSError: pass
                        continue
                    if type_ != EV_KEY:
                        continue
                    if code == ctrl:
                        if value == 0:
                            if state == "pending":
                                press_select(1); time.sleep(0.05)  # a real button press lasts a moment
                                press_select(0)
                                print("click", flush=True)
                            else:
                                press_select(0)
                                print("release", flush=True)
                            ctrl, state = None, None
                        continue  # repeats of a held-back Control are dropped too
                    if value == 1 and ctrl is None and not held and code in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
                        ctrl, ctrl_since, state = code, time.monotonic(), "pending"
                        continue
                    if value == 1 and ctrl is not None:
                        flush_ctrl()
                    (held.add if value else held.discard)(code)
                    emit(kbd, EV_KEY, code, value)
    finally:
        if state == "drag":
            press_select(0)
        fcntl.ioctl(fake, UI_DEV_DESTROY)
        fcntl.ioctl(kbd, UI_DEV_DESTROY)

if __name__ == "__main__":
    main()
