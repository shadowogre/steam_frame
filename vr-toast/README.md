# vr-toast

Send a message to the Steam Frame and it pops up in VR, floating in front of you.

```bash
vrtoast "dinner is ready"
vrtoast -t 15 "stays up for 15 seconds"
echo "from a pipe" | vrtoast
vrtoast "line one\nline two"      # \n (or a real newline) makes a line break
```

## Sending from another computer

Over ssh, give the full path to the command. A plain `vrtoast` is "not found", because
ssh doesn't read `~/.bashrc`, which is where `~/.local/bin` gets added to the PATH:

```bash
ssh steamos@frame.local '~/.local/bin/vrtoast "hello from my laptop"'
ssh steamos@frame.local '~/.local/bin/vrtoast --place'
```

Keep the single quotes around the whole command so your own computer doesn't try to
expand `~` itself.

Messages sent close together **stack** (up to 6 cards at once) instead of replacing
each other. Extra ones wait their turn. Each card goes away on its own after a few
seconds (longer messages stay longer), or after `-t` seconds if you give one.

If SteamVR isn't running, the message shows as a normal desktop notification instead,
so nothing is lost.

## Install

```bash
./install.sh            # see ./install.sh --help for position/size options
./install.sh --uninstall
```

It needs `python-cairo` (the installer tells you how to get it if it's missing) and
starts automatically with SteamVR. The `vrtoast` command is linked into `~/.local/bin`. It waits for SteamVR to finish starting first (`wait-for-vr.sh`, kept in this folder so the project stays self-contained), because an overlay that starts too early can race the headset's display startup.

## Placing the popups

Run `vrtoast --place`. A card appears in your view: point a controller
at it, hold the trigger, move it where you want your popups, and let go. The spot is
remembered. It also shows up on its own the first time, until you have placed it once.

How long the card stays:

- **60 seconds** after you run `vrtoast --place`, if you haven't picked it up. It stays for
  as long as you're holding it.
- **15 seconds** after you let go, so you can read where it landed and how the popups will
  stack. You can grab it again within those 15 seconds.
- Run `vrtoast --place` again at any time to bring it back.

- Card **high**: popups stack downward. **Low**: they stack upward. **In between**: the
  stack grows both ways around it.
- Card **left or right** of centre: popups sit there and the text lines up that way.
- `--vertical` / `--horizontal` at install time force a direction instead.
- Reset by deleting `~/.config/vr-toast.json`.

## How long cards stay

By default a card stays for a time that grows with the message length (at least 3 seconds).

```bash
vrtoast -t quick "..."    # 0.05 seconds per character
vrtoast -t normal "..."   # 0.08 (the default)
vrtoast -t long "..."     # 0.13
vrtoast -t 12 "..."       # exactly 12 seconds
```

To change the default for every message, install with `./install.sh --time long` (or a
number of seconds).

## Notes

- Named `vrtoast` because `toast` is already a different program on SteamOS (an audio compressor).
- The popups are pinned to your head, like the clock.
