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

# The persistent registry login the units read; a reboot keeps it.
export REGISTRY_AUTH_FILE="${REGISTRY_AUTH_FILE:-$APP_DIR/ghcr-auth.json}"

# The start order of the stack. The metasearch, the two tool servers and the
# trace store are required by no application unit, so the installer starts
# every one of them.
SERVICES=(
  pathfinder-db.service
  pathfinder-langfuse-db.service
  pathfinder-langfuse-clickhouse.service
  pathfinder-langfuse-minio.service
  pathfinder-langfuse-redis.service
  pathfinder-langfuse-worker.service
  pathfinder-langfuse.service
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
# The keys a committed example declares that the operator's file does not,
# one per line. A key with an empty value is declared.
missing_env_keys() {
  local example="$1" actual="$2"
  comm -23 \
    <(grep -o '^[A-Z_][A-Z0-9_]*=' "$example" | sort -u) \
    <(grep -o '^[A-Z_][A-Z0-9_]*=' "$actual" | sort -u) \
    | tr -d '='
}

# Refuses an env file that lacks a key its example declares: a setting the
# units read and the file does not name is a feature silently off.
check_env_keys() {
  local example="$1" actual="$2" missing
  missing="$(missing_env_keys "$example" "$actual")"
  if [ -n "$missing" ]; then
    echo "$actual lacks keys $example declares; add them (an empty value is allowed):" >&2
    echo "$missing" | sed 's/^/  /' >&2
    exit 1
  fi
}

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

# The checkpoint tables hold the shape of a turn's state as the release that
# wrote it laid it out. A release that changes that shape cannot read them, so
# the operator passes --purge-checkpoints on that bump and every thread starts
# its next turn from its persisted events instead.
purge_checkpoints() {
  systemctl --user start pathfinder-db.service
  local attempt
  for attempt in $(seq 1 30); do
    if podman exec pathfinder-db pg_isready -U postgres > /dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  podman exec -i pathfinder-db psql -U postgres -d pathfinder -v ON_ERROR_STOP=1 \
    -c "TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes"
  echo "purged the checkpoint tables"
}

main() {
  local purge=0
  if [ "${1:-}" = "--purge-checkpoints" ]; then
    purge=1
  elif [ -n "${1:-}" ]; then
    echo "usage: PATHFINDER_TAG=<tag> $0 [--purge-checkpoints]" >&2
    exit 2
  fi
  mkdir -p "$UNIT_DIR" "$APP_DIR/searxng"

  if [ ! -f "$APP_DIR/.env" ]; then
    echo "no $APP_DIR/.env: copy deploy/cedar/env.example there and fill it in" >&2
    exit 1
  fi
  if [ ! -f "$APP_DIR/langfuse.env" ]; then
    echo "no $APP_DIR/langfuse.env: copy deploy/cedar/langfuse.env.example there and fill it in" >&2
    exit 1
  fi
  check_env_keys "$REPO_ROOT/deploy/cedar/env.example" "$APP_DIR/.env"
  check_env_keys "$REPO_ROOT/deploy/cedar/langfuse.env.example" "$APP_DIR/langfuse.env"

  install_units

  # The stack must survive a logout and come back after a reboot.
  loginctl enable-linger "$(id -un)"
  systemctl --user daemon-reload

  if [ "$purge" -eq 1 ]; then
    purge_checkpoints
  fi
  start_stack

  # status reports a non-zero code for a unit that is not running, which is
  # what the operator is here to read.
  systemctl --user --no-pager status "${SERVICES[@]}" || true
}

# Sourcing the file defines its functions and runs nothing.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
