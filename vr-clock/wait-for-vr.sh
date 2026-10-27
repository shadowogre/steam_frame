#!/bin/bash
# Holds an overlay service back until SteamVR is properly up.
#
# An OpenVR overlay app starts vrserver itself if it isn't running yet. When
# that happens during boot, it races gamescope's own startup, and gamescope
# has crashed in a loop (black screen) after losing that race. So wait for
# gamescope to finish starting and for Valve's own startup to bring vrserver
# up, and only then let the overlay connect.
#
# Exits 1 after ~2 minutes so the service's Restart=always tries again.
for _ in $(seq 120); do
    if systemctl --user is-active --quiet gamescope-session.service && pgrep -x vrserver >/dev/null; then
        sleep 2   # let vrserver finish its own setup
        exit 0
    fi
    sleep 1
done
echo "wait-for-vr: gamescope/vrserver not ready after 120s" >&2
exit 1
