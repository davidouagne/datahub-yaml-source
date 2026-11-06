# shellcheck shell=bash
# Data isolation for a local DataHub server, shared by
# verify-datahub-version.sh and datahub-local.sh. Source it, don't run it.
#
# Adapted from datahub-healthdcat-ap-exporter's scripts/lib/datahub-isolation.sh
# at commit 0d8944d9dc27 (ADR-0007 §8: copied, not shared across repos --
# resync by hand when the exporter's copy changes).
#
# The official quickstart compose hard-codes its volume names
# (`datahub_mysqldata`, `datahub_osdata`, `datahub_broker`), so another project
# name is NOT enough: a server of another version would start on the data of
# an existing quickstart. We download that compose, rename its volumes after
# the project, refuse to start if a server already answers on 8080, and check
# the mounted volumes before any write.
#
# Expects `root` (repository root); `isolation_env` sets the compose project.
# shellcheck disable=SC2154

step() { printf '\n== %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

dh() { uv run --project "$root" datahub "$@"; }

# isolation_env <project>: a compose project of its own (isolated volumes and
# network).
isolation_env() {
  export DATAHUB_COMPOSE_PROJECT_NAME="$1"
  # Always the local server, never ~/.datahubenv (which may point at another
  # server); the quickstart doesn't enable authentication.
  export DATAHUB_GMS_URL="http://localhost:8080"
  export DATAHUB_GMS_TOKEN=""
  # Redirected output on Windows: without UTF-8 the datahub CLI crashes
  # printing "✔" (cp1252). Standard streams only: PYTHONUTF8 would also change
  # file encoding, and the CLI could no longer read its
  # ~/.datahub/quickstart/.local-secrets.env, written in the local encoding.
  export PYTHONIOENCODING=utf-8
}

gms_up() {
  curl -sf -o /dev/null --max-time 5 "$DATAHUB_GMS_URL/health"
}

# fetch_isolated_compose <version> <file>: the quickstart compose, its volumes
# renamed after the project.
fetch_isolated_compose() {
  local version="$1" compose="$2" git_ref
  step "Quickstart compose $version, volumes renamed for project $DATAHUB_COMPOSE_PROJECT_NAME"
  # The same compose `datahub docker quickstart --version` would download: its
  # version table can point at another git ref than the tag (v1.7.0 ->
  # v1.7.0.1), whose own compose doesn't start.
  git_ref="$(uv run --project "$root" python -c "
from datahub.cli.quickstart_versioning import QuickstartVersionMappingConfig as Q
print(Q.fetch_quickstart_config().get_quickstart_execution_plan('v$version').composefile_git_ref)
" 2>/dev/null | tail -1)"
  [ -n "$git_ref" ] || die "no quickstart plan for v$version"
  curl -sfL -o "$compose" \
    "https://raw.githubusercontent.com/datahub-project/datahub/$git_ref/docker/quickstart/docker-compose.quickstart-profile.yml" \
    || die "no compose for $git_ref"
  echo "Compose of ref $git_ref"
  sed -i "s/^    name: datahub_/    name: ${DATAHUB_COMPOSE_PROJECT_NAME}_/" "$compose"
  if grep -q "name: datahub_" "$compose"; then
    die "a datahub_* volume is left in the compose: cannot isolate"
  fi
}

project_filter() { echo "label=com.docker.compose.project=$DATAHUB_COMPOSE_PROJECT_NAME"; }

project_running() {
  [ -n "$(docker ps -q --filter "$(project_filter)")" ]
}

# stop_isolated: stops the project's containers, keeping its data.
stop_isolated() {
  docker ps -q --filter "$(project_filter)" | xargs -r docker stop >/dev/null
}

# purge_isolated: removes the project's containers, volumes and network, and
# only those. Not `datahub docker nuke`: whatever the project, it also removes
# a default quickstart's `datahub_mysqldata`, `datahub_broker`... volumes.
purge_isolated() {
  docker ps -aq --filter "$(project_filter)" | xargs -r docker rm -f -v >/dev/null
  docker volume ls -q --filter "$(project_filter)" \
    | { grep "^${DATAHUB_COMPOSE_PROJECT_NAME}_" || true; } \
    | xargs -r docker volume rm >/dev/null
  docker network ls -q --filter "$(project_filter)" | xargs -r docker network rm >/dev/null
}

# start_isolated <version> <file>: starts the server, then checks MySQL mounts
# the project's volume (last guard before any write).
start_isolated() {
  local version="$1" compose="$2" mounts
  step "Starting DataHub server $version"
  dh docker quickstart --version "v$version" --no-accept-version-default -f "$compose"
  mounts="$(docker inspect "$DATAHUB_COMPOSE_PROJECT_NAME-mysql-1" --format '{{range .Mounts}}{{.Name}} {{end}}')"
  case "$mounts" in
    *"${DATAHUB_COMPOSE_PROJECT_NAME}_mysqldata"*) ;;
    *) die "MySQL mounts '$mounts', not the project's volume: stopping before any write." ;;
  esac
}
