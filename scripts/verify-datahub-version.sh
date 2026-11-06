#!/usr/bin/env bash
# Version check of a DataHub server version (ADR-0007 §3).
#
#   scripts/verify-datahub-version.sh <version> [--keep]
#
#   <version>   server version, e.g. 1.7.0
#   --keep      leave the server running (otherwise removed, volumes included)
#
# Starts the server in Docker under a compose project of its own, ingests
# tests/integration/yaml_source/resources through datahub-rest (mode SYNC),
# then reads every emitted aspect back and checks the server kept it
# (scripts/version_check.py). Exit 0 means this minor can be called a
# Supported DataHub version.
#
# Never run in CI (ADR-0007 §3). Needs Docker with ~8 GB of RAM, and ports
# 8080/9002/3306/9092/9200 free (stop any other DataHub quickstart first). On
# Windows, run it from Git Bash.
#
# Data isolation: volumes of the project `dhys-verify-<version>`, see
# scripts/lib/datahub-isolation.sh.
set -euo pipefail

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

version=""
keep=false
for arg in "$@"; do
  case "$arg" in
    --keep) keep=true ;;
    -h | --help) usage ;;
    -*) echo "Unknown option: $arg" >&2; usage ;;
    *) [ -z "$version" ] && version="${arg#v}" || usage ;;
  esac
done
[ -n "$version" ] || usage

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/datahub-isolation.sh
. "$root/scripts/lib/datahub-isolation.sh"
work="$(mktemp -d)"

isolation_env "dhys-verify-${version//./-}"

cleanup() {
  rm -rf "$work"
  if [ "$keep" = false ]; then
    step "Removing server $version (project $DATAHUB_COMPOSE_PROJECT_NAME)"
    purge_isolated || true
  else
    echo "Server left running. Stop it: scripts/datahub-local.sh $version down --purge --project $DATAHUB_COMPOSE_PROJECT_NAME"
  fi
}
trap cleanup EXIT

if gms_up; then
  trap - EXIT
  rm -rf "$work"
  die "a DataHub server already answers on $DATAHUB_GMS_URL: stop it before the check (nothing written)."
fi

compose="$work/docker-compose.yml"
fetch_isolated_compose "$version" "$compose"
start_isolated "$version" "$compose"

step "Ingest the fixture, then read it back"
# From the repository root: version_check.py passes relative paths, which the
# file-based pieces of DataHub need on Windows.
(cd "$root" && uv run --project "$root" python scripts/version_check.py --server "$DATAHUB_GMS_URL")
