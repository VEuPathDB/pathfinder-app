#!/usr/bin/env bash
# The e2e suite on recorded WDK answers.
#   replay [playwright args]       the suite against apps/web/e2e/wire (Mac, CI)
#   catalogs                       build the catalog snapshots from QA (cedar only)
#   record --test <spec:line> ...  record the named tests against QA (cedar only)
#   record --all                   record the whole suite (cedar only)
#   refresh                        re-send every recording to QA (cedar only)
# record and refresh read WDK_TEST_EMAIL and WDK_TEST_PASSWORD from the shell.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${E2E_ENV_FILE:-.env.test}"
WIRE="apps/web/e2e/wire"
REPLAY_FILES=(-f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.e2e-wire.yml)
RECORD_FILES=("${REPLAY_FILES[@]}" -f docker-compose.e2e-wire-record.yml)
SERVICES=(wdk-wire api worker web)
READY_TRIES=150

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

need_account() {
  if [ -z "${WDK_TEST_EMAIL:-}" ] || [ -z "${WDK_TEST_PASSWORD:-}" ]; then
    echo "export WDK_TEST_EMAIL and WDK_TEST_PASSWORD first" >&2
    exit 2
  fi
}

wait_for_stack() {
  for _ in $(seq 1 "$READY_TRIES"); do
    if curl -fsS http://localhost:8000/health/ready > /dev/null 2>&1 \
      && curl -fsS http://localhost:3000/strategist/ > /dev/null 2>&1 \
      && curl -fsS http://localhost:8000/health/system | grep -q '"workerAlive":true'; then
      return 0
    fi
    sleep 4
  done
  echo "the stack did not become ready" >&2
  compose "${REPLAY_FILES[@]}" logs --no-color --tail 80 wdk-wire api worker >&2
  return 1
}

start_replay() {
  WIRE_DIR="$1" compose "${REPLAY_FILES[@]}" up -d --build --force-recreate "${SERVICES[@]}"
  wait_for_stack
}

suite() {
  (cd apps/web && E2E_WIRE="$1" corepack yarn playwright test "${@:2}")
}

replay() {
  start_replay "./$WIRE"
  suite replay "$@"
}

TESTS=()
ALL=""

read_tests() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --test) TESTS+=("$2"); shift 2 ;;
      --all) ALL=1; shift ;;
      *) echo "record takes --test <spec:line> or --all, not $1" >&2; exit 2 ;;
    esac
  done
  if [ "${#TESTS[@]}" -eq 0 ] && [ -z "$ALL" ]; then
    echo "name at least one --test <spec:line>, or --all" >&2
    exit 2
  fi
  if [ ! -d "$WIRE/catalogs" ]; then
    echo "build the catalog snapshots first: scripts/e2e-wire.sh catalogs" >&2
    exit 2
  fi
}

wire_command() {
  local mounts=("$@")
  compose "${RECORD_FILES[@]}" run --rm --no-deps -T \
    -e WDK_TEST_EMAIL -e WDK_TEST_PASSWORD "${mounts[@]}" wdk-wire
}

record() {
  need_account
  read_tests "$@"
  local staging scratch status=0
  staging="$(mktemp -d)"
  scratch="$(mktemp -d)"
  trap 'rm -rf "$staging" "$scratch"' EXIT

  WIRE_DIR="$staging" WIRE_ACCESS=rw \
    compose "${RECORD_FILES[@]}" up -d --build --force-recreate "${SERVICES[@]}"
  wait_for_stack
  suite record ${TESTS[@]+"${TESTS[@]}"} || status=$?
  node apps/web/scripts/redact-traces.mjs apps/web/test-results apps/web/playwright-report

  cp -R "$WIRE/." "$scratch/"
  wire_command -v "$staging:/staging:ro" -v "$scratch:/scratch" \
    python -m veupathdb.testing.wire merge /staging /scratch

  start_replay "$scratch"
  suite replay ${TESTS[@]+"${TESTS[@]}"}

  rm -rf "${WIRE:?}"
  cp -R "$scratch/." "$WIRE/"
  node scripts/check-wire-recordings.mjs
  return "$status"
}

build_catalogs() {
  local project=strategist-catalogs
  local built
  built="$(mktemp -d)"
  compose -p "$project" -f docker-compose.yml -f docker-compose.e2e.yml \
    up -d --build db api
  local loaded=""
  for _ in $(seq 1 "$READY_TRIES"); do
    if curl -fsS http://localhost:8000/api/v1/sites 2>/dev/null \
      | python3 -c 'import json, sys; sys.exit(0 if all(s["available"] for s in json.load(sys.stdin)) else 1)'; then
      loaded=1
      break
    fi
    sleep 4
  done
  if [ -z "$loaded" ]; then
    compose -p "$project" -f docker-compose.yml -f docker-compose.e2e.yml logs --no-color --tail 80 api >&2
    compose -p "$project" -f docker-compose.yml -f docker-compose.e2e.yml down -v
    echo "QA did not answer every catalog; the old snapshots stay" >&2
    return 1
  fi
  compose -p "$project" cp api:/app/data/catalogs/. "$built/"
  compose -p "$project" -f docker-compose.yml -f docker-compose.e2e.yml down -v
  mkdir -p "$WIRE/catalogs"
  for snapshot in "$built"/*.json; do
    gzip -n -c "$snapshot" > "$WIRE/catalogs/$(basename "$snapshot").gz"
  done
  rm -rf "$built"
}

refresh() {
  need_account
  local reports status=0
  reports="$(mktemp -d)"
  compose "${REPLAY_FILES[@]}" down
  compose "${RECORD_FILES[@]}" build wdk-wire
  WIRE_DIR="$ROOT/$WIRE" WIRE_ACCESS=rw wire_command -v "$reports:/reports" \
    python -m veupathdb.testing.wire refresh /wire/recordings \
    --sites /wire/sites.yaml --report /reports/refresh-report.md || status=$?
  cp "$reports/refresh-report.md" "$ROOT/refresh-report.md"
  rm -rf "$reports"
  build_catalogs
  node scripts/check-wire-recordings.mjs
  replay || status=$?
  echo "refresh report: $ROOT/refresh-report.md"
  return "$status"
}

case "${1:-}" in
  replay) shift; replay "$@" ;;
  catalogs) compose "${REPLAY_FILES[@]}" down; build_catalogs ;;
  record) shift; record "$@" ;;
  refresh) shift; refresh "$@" ;;
  *) echo "usage: scripts/e2e-wire.sh replay|catalogs|record (--test <spec:line> | --all)|refresh" >&2; exit 2 ;;
esac
