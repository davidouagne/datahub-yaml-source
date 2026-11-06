#!/usr/bin/env bash
# An empty local DataHub server, isolated per version, to inspect by hand.
#
#   scripts/datahub-local.sh <version> up|down [--purge] [--project <name>]
#
#   <version>          server version, e.g. 1.7.0 or 1.8.0
#   up                 start (or restart, with its data) this version
#   down               stop the server, keeping its data
#   --purge            with down: also remove containers, volumes and network
#   --project <name>   compose project (default: dhys-local-<version>), e.g.
#                      dhys-verify-<version> left by verify-datahub-version.sh --keep
#
# No ingestion, no read-back: see verify-datahub-version.sh for the Version
# check. One version at a time, on the default ports (UI 9002, GMS 8080): `up`
# refuses to start if another server already answers on 8080. Needs Docker
# with ~8 GB of RAM; on Windows, run it from Git Bash.
#
# Ported from datahub-healthdcat-ap-exporter's scripts/datahub-local.sh at
# commit 0d8944d9dc27 (ADR-0007 §8). Data isolation: volumes of the project,
# see scripts/lib/datahub-isolation.sh. The compose is kept under
# ~/.datahub/dhys-local/<project>/ to restart on the same data.
set -euo pipefail

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

version=""
action=""
purge=false
project=""
while [ $# -gt 0 ]; do
  case "$1" in
    up | down) [ -z "$action" ] && action="$1" || usage ;;
    --purge) purge=true ;;
    --project) [ $# -ge 2 ] || usage; project="$2"; shift ;;
    -h | --help) usage ;;
    -*) echo "Unknown option: $1" >&2; usage ;;
    *) [ -z "$version" ] && version="${1#v}" || usage ;;
  esac
  shift
done
[ -n "$version" ] && [ -n "$action" ] || usage
[ "$purge" = false ] || [ "$action" = down ] || usage

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/datahub-isolation.sh
. "$root/scripts/lib/datahub-isolation.sh"

isolation_env "${project:-dhys-local-${version//./-}}"
state="$HOME/.datahub/dhys-local/$DATAHUB_COMPOSE_PROJECT_NAME"
compose="$state/docker-compose.yml"

if [ "$action" = down ]; then
  if [ "$purge" = true ]; then
    step "Removing server $version (project $DATAHUB_COMPOSE_PROJECT_NAME), volumes included"
    purge_isolated
    rm -rf "$state"
  else
    step "Stopping server $version (project $DATAHUB_COMPOSE_PROJECT_NAME), data kept"
    stop_isolated
  fi
  exit 0
fi

if project_running && gms_up; then
  echo "Server $version (project $DATAHUB_COMPOSE_PROJECT_NAME) is already running."
  exit 0
fi
if gms_up; then
  die "another DataHub server already answers on $DATAHUB_GMS_URL: stop it first (nothing written)."
fi

mkdir -p "$state"
if [ ! -s "$compose" ]; then
  fetch_isolated_compose "$version" "$compose"
fi
start_isolated "$version" "$compose"

cat <<EOF

DataHub $version ready (project $DATAHUB_COMPOSE_PROJECT_NAME).
  UI:  http://localhost:9002 (datahub / datahub)
  GMS: $DATAHUB_GMS_URL
  Stop: scripts/datahub-local.sh $version down [--purge]
EOF
