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
./install.sh --mode wrist              # left hand
./install.sh --mode wrist --hand right
```

It appears when you turn your wrist towards your face and hides again when you look away, so it never clutters a game. Add `--always` to keep it visible all the time. If it flickers at the edge of a glance or is slow to show, change `--glance` (0 to 1; lower shows it more easily, default 0.5). To move it on your wrist, point your other controller at it with the dashboard open and hold the trigger. Run `./install.sh` with no options to go back to the floating view.

## Adjust it

Run with `--help` to see every option. Common ones:

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
