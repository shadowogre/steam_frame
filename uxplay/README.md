# UxPlay on the Steam Frame

AirPlay screen-mirroring receiver. Runs inside a Debian container (distrobox) in
`$HOME`, because SteamOS updates wipe anything installed with pacman.

    ./install.sh      # set up (idempotent; first run takes a few minutes)
    ./uninstall.sh    # remove everything it installed

Start: the **UxPlay** desktop icon, or `distrobox enter debian -- uxplay`.

## Snags the script already handles
- **No distrobox on SteamOS** – installed to `~/.local` from the pinned v1.8.2.5 release (downloaded to a file, not piped into `sh`).
- **`No DNS-SD Server found`** – avahi's client talks to the host's avahi over D-Bus, which containers lack. The container is created with the host's `/run/dbus/system_bus_socket` mounted in. (Don't install `avahi-daemon` in the container; it uses the host's.)
- **`gstreamer1.0-vaapi` not available** – dropped from Debian testing; not needed.
- **`NameConflict` on start** – an earlier UxPlay is still running (`pkill -x uxplay`).
- A `Failed to add pause process to systemd sandbox cgroup` podman warning is harmless.

Only Valve's `lepton-*` podman containers are left untouched by uninstall.
