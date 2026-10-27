# vr-clock

A small floating panel showing the time and battery level, pinned to the lower left of your view in every game and on the desktop (like the Performance HUD, but just the two things you want).

It draws the panel with cairo and shows it as an OpenVR overlay (in VR, an overlay is always a flat picture; there is no text-only option). It checks the time and battery every 5 seconds and only redraws when what's shown has changed.

## Try it

```bash
./install.sh
```

This creates a private Python environment (`.venv`), then starts the overlay as a user service that launches with SteamVR. Undo with `./install.sh --uninstall`.

## Move it

Open the SteamVR dashboard or Steam menu (so your controllers show their pointer lasers), point at the panel, hold the trigger, move it, and let go. It pins itself to your view in the new spot, and the spot is remembered in `~/.config/vr-clock.json`. In a game it can't be grabbed, on purpose: making it pointable during games takes over the controllers. Delete that file to go back to the default position.

## Wrist watch mode

Instead of floating in your view, the clock can ride on a controller like a watch:

```bash
./install.sh --mode wrist              # left wrist
./install.sh --mode wrist --hand right # right wrist
```

It appears when you turn your wrist towards your face and hides again when you look away, so it never clutters a game. The controller needs to be on and tracked.

| Option | Meaning |
| --- | --- |
| `--hand left\|right` | which wrist (default left); only one wrist at a time |
| `--always` | keep it visible all the time, not just when you look at your wrist |
| `--glance 0.5` | how squarely your wrist must face you to show it, 0 to 1. Lower shows it more easily; raise it if it pops up when you don't want it |

**Positioning it.** Open the SteamVR dashboard, point your *other* controller at the clock (the one not wearing it), hold the trigger to carry it, and let go to drop it. Tilt it so it faces you like a watch face. The spot is saved in `~/.config/vr-clock.json`, so it survives restarts. Like the floating clock, it can't be grabbed during a game.

**Switching wrists** forgets the saved spot, since a position that suits one wrist would be mirrored on the other; just grab and place it again. Delete `~/.config/vr-clock.json` to reset the position by hand.

Running `./install.sh` with no options goes back to the floating view. Options are saved into the service when you install, so repeat your wrist options each time you reinstall.

## Adjust it

Run `./install.sh --help` to see the installer's options. The ones below work when added to the service by hand, as described underneath (`--x`, `--y` and `--distance` only apply to the floating clock):

| Option | Meaning |
| --- | --- |
| `--24h` | 24-hour time |
| `--x -0.30` | metres right of centre (negative = left) |
| `--y -0.22` | metres above centre (negative = below) |
| `--distance 1.0` | metres in front of your face |
| `--width 0.18` | panel size in metres |
| `--opacity 0.9` | 0 to 1 |
| `--refresh 5` | seconds between time/battery checks |

To make a setting stick, add it to the `ExecStart=` line in `~/.config/systemd/user/vr-clock.service` (or edit `install.sh` and re-run it), then `systemctl --user restart vr-clock`.

The battery turns green while charging and red at 20% or below.
