# aux-shortcut

Use **Control** on any keyboard (tested with a Bluetooth Magic Keyboard) as the
Steam Frame's Aux/Select button:

| You do | It does |
| --- | --- |
| Tap Control by itself | Click (press and release Select) |
| Hold Control by itself (> 0.3 s) | Hold Select, so you can drag; let go of Control to release |
| Control + another key | A normal shortcut (Ctrl+C etc.) |

## How it works

`aux_shortcut.py` creates a virtual input device that copies the headset's real Aux
button (`gpio-keys`, key `KEY_SELECT`), so SteamVR treats it like the real thing.
It also grabs your keyboards and passes their keys through a virtual
"aux-shortcut keyboard", holding Control back until it's clear whether you meant a
tap, a hold, or a shortcut, so the desktop never sees a stray Ctrl-click.

SteamVR only looks for input devices when it starts, so the script has to be running
before SteamVR does. The install script takes care of that.

## Install

Your user must be in the `input` group so the script can read the keyboard
(`install.sh` warns you if it isn't).

```bash
git clone https://github.com/shadowogre/steam_frame.git
cd steam_frame/aux-shortcut
./install.sh
systemctl --user restart steamvr.service   # once, so SteamVR notices the button
```

Don't move or delete the folder afterwards: the service runs the script from there.
If you do move it, run `./install.sh` again from the new location.

This adds a user service, `aux-shortcut.service`, that starts just before SteamVR on
every boot. To remove it:

```bash
./install.sh --uninstall
```

## Troubleshooting

- Is it running? `systemctl --user is-active aux-shortcut`
- What's it doing? `cat log.txt` (in this folder) shows each click/release.
- If you run `systemctl --user` from a terminal inside VR and get errors, run
  `export XDG_RUNTIME_DIR=/run/user/$(id -u)` first.
- Setting `AUX_ONLY_KEYBOARD=<device name>` limits the script to one keyboard
  (useful for testing).
