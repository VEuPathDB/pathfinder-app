#!/usr/bin/env bash
# Installs the PathFinder quadlet units for one rootless podman user.
#
# Reads PATHFINDER_TAG, the release the units pull from the registry. Run it
# again after a tag bump: it rewrites only the files that changed and restarts
# only the units behind them.
set -euo pipefail

: "${PATHFINDER_TAG:?set PATHFINDER_TAG to the release to run, for example v0.2.0a2}"

TAG_PLACEHOLDER='__PATHFINDER_TAG__'
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONFIG_HOME/containers/systemd"
APP_DIR="$CONFIG_HOME/pathfinder"
readonly TAG_PLACEHOLDER REPO_ROOT CONFIG_HOME UNIT_DIR APP_DIR

# The start order of the stack. The metasearch and the two tool servers are
# required by no other unit, so the installer starts every one of them.
SERVICES=(
  pathfinder-db.service
  pathfinder-wdk-mcp.service
  pathfinder-searxng.service
  pathfinder-research-mcp.service
  pathfinder-api.service
  pathfinder-worker.service
  pathfinder-web.service
)
readonly SERVICES

# The services whose unit file this run rewrote, and whether the network, a
# volume or the metasearch settings changed under every unit.
changed_services=()
shared_changed=0
# The directory the tag substitution writes to, removed when the script ends.
rendered=""

# Writes $2 to $1 when the content differs. Returns 1 when it wrote nothing.
install_file() {
  local destination="$1" source="$2"
  if [ -f "$destination" ] && cmp -s "$source" "$destination"; then
    return 1
  fi
  # The destination may be a symlink into a checkout, which a plain copy would
  # write through.
  rm -f "$destination"
  cp "$source" "$destination"
  chmod 0644 "$destination"
  echo "wrote $destination"
  return 0
}

contains() {
  local needle="$1" item
  shift
  for item in "$@"; do
    [ "$item" = "$needle" ] && return 0
  done
  return 1
}

# The generator rejects a unit it cannot render before anything is installed.
validate_units() {
  local generator=/usr/libexec/podman/quadlet
  [ -x "$generator" ] || return 0
  QUADLET_UNIT_DIRS="$1" "$generator" -dryrun -user > /dev/null
}

# A restart is down only for the switch, not for the download.
pull_image() {
  local image
  image="$(sed -n 's/^Image=//p' "$UNIT_DIR/${1%.service}.container")"
  [ -n "$image" ] || return 0
  podman pull --quiet "$image" > /dev/null
}

install_units() {
  local unit name
  rendered="$(mktemp -d)"
  trap 'rm -rf "$rendered"' EXIT

  for unit in "$REPO_ROOT"/quadlets/*.container; do
    name="$(basename "$unit")"
    sed "s|$TAG_PLACEHOLDER|$PATHFINDER_TAG|g" "$unit" > "$rendered/$name"
  done
  for unit in "$REPO_ROOT"/quadlets/*.network "$REPO_ROOT"/quadlets/*.volume; do
    [ -e "$unit" ] || continue
    cp "$unit" "$rendered/"
  done
  validate_units "$rendered"

  for unit in "$rendered"/*.container; do
    name="$(basename "$unit")"
    if install_file "$UNIT_DIR/$name" "$unit"; then
      changed_services+=("${name%.container}.service")
    fi
  done

  for unit in "$REPO_ROOT"/quadlets/*.network "$REPO_ROOT"/quadlets/*.volume; do
    [ -e "$unit" ] || continue
    if install_file "$UNIT_DIR/$(basename "$unit")" "$unit"; then
      shared_changed=1
    fi
  done
  if install_file "$APP_DIR/searxng/settings.yml" "$REPO_ROOT/deploy/searxng/settings.yml"; then
    shared_changed=1
  fi
  return 0
}

start_stack() {
  local service
  for service in "${SERVICES[@]}"; do
    if [ "$shared_changed" -eq 1 ] || contains "$service" "${changed_services[@]}"; then
      pull_image "$service"
      systemctl --user restart "$service"
    else
      # A unit that already runs the same file is left alone.
      systemctl --user start "$service"
    fi
  done
}

main() {
  mkdir -p "$UNIT_DIR" "$APP_DIR/searxng"

  if [ ! -f "$APP_DIR/.env" ]; then
    echo "no $APP_DIR/.env: copy deploy/cedar/env.example there and fill it in" >&2
    exit 1
  fi

  install_units

  # The stack must survive a logout and come back after a reboot.
  loginctl enable-linger "$(id -un)"
  systemctl --user daemon-reload

  start_stack

  # status reports a non-zero code for a unit that is not running, which is
  # what the operator is here to read.
  systemctl --user --no-pager status "${SERVICES[@]}" || true
}

main "$@"
