#!/usr/bin/env bash
# Run a SonarQube analysis of this repo against the local SonarQube container.
#
#   SONAR_TOKEN=<token> ./sonarqube/scan.sh
#
# If SONAR_TOKEN is not set, it is read from sonarqube/.env (gitignored).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "${SONAR_TOKEN:-}" && -f "$repo_root/sonarqube/.env" ]]; then
  # shellcheck disable=SC1091
  source "$repo_root/sonarqube/.env"
fi
: "${SONAR_TOKEN:?SONAR_TOKEN not set (and sonarqube/.env not found)}"
: "${SONAR_HOST_URL:=http://localhost:9000}"

exec podman run --rm --network host \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  -v "$repo_root:/usr/src:Z" \
  docker.io/sonarsource/sonar-scanner-cli
