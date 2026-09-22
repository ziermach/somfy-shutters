#!/bin/sh
# Update /opt/somfy-shutters to a GitHub release, without Node on the Pi.
#
#   sh /opt/somfy-shutters/deploy/update.sh           # newest release tag
#   sh /opt/somfy-shutters/deploy/update.sh v0.2.0    # a given one
#
# Run it as your own login (it uses sudo). The code comes from the tag, the built
# frontend from that release's frontend-dist.tar.gz (.github/workflows/release.yml).
set -eu

APP=/opt/somfy-shutters
REPO=ziermach/somfy-shutters
as_app() { sudo -u somfy "$@"; }

as_app git -C "$APP" fetch --quiet --tags origin
tag=${1:-$(as_app git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n 1)}
[ -n "$tag" ] || { echo "no release tag found" >&2; exit 1; }
echo "updating to $tag"

# Download and verify before stopping anything: a failed download leaves the app running.
work=$(as_app mktemp -d)
trap 'sudo rm -rf "$work"' EXIT
url="https://github.com/$REPO/releases/download/$tag"
as_app curl -fsSL -o "$work/frontend-dist.tar.gz" "$url/frontend-dist.tar.gz"
as_app curl -fsSL -o "$work/frontend-dist.tar.gz.sha256" "$url/frontend-dist.tar.gz.sha256"
as_app sh -c 'cd "$1" && sha256sum -c --quiet frontend-dist.tar.gz.sha256' _ "$work"
as_app mkdir "$work/dist"
as_app tar -xzf "$work/frontend-dist.tar.gz" -C "$work/dist"

sudo systemctl stop somfy-shutters
as_app git -C "$APP" checkout --quiet "$tag"
as_app "$APP/backend/.venv/bin/pip" install --quiet -e "$APP/backend"
as_app rm -rf "$APP/frontend/dist"
as_app mv "$work/dist" "$APP/frontend/dist"
sudo cp "$APP/deploy/somfy-shutters.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start somfy-shutters
echo "running $tag"
