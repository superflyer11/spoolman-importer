#!/bin/bash
# Deletes all spools from Spoolman.
#
# Usage:
#   ./delete_all_spools.sh [--dry-run] [SPOOLMAN_URL]
#
# Example:
#   ./delete_all_spools.sh --dry-run http://localhost:7912

set -euo pipefail

DRY_RUN=false
SPOOLMAN_URL="http://localhost:7912"

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=true
      ;;
    -h|--help)
      sed -n '2,11p' "$0"
      exit 0
      ;;
    *)
      SPOOLMAN_URL="${arg%/}"
      ;;
  esac
done

command -v jq >/dev/null 2>&1 || {
  echo "Error: jq is required." >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "Error: curl is required." >&2
  exit 1
}

API_URL="$SPOOLMAN_URL/api/v1/spool"
RESPONSE=$(curl --fail --silent --show-error "$API_URL")
IDS=$(printf '%s\n' "$RESPONSE" | jq -r '.[].id')
COUNT=$(printf '%s\n' "$IDS" | sed '/^$/d' | wc -l | tr -d ' ')

if [ "$COUNT" = "0" ]; then
  echo "No spools found at $SPOOLMAN_URL."
  exit 0
fi

echo "Target: $SPOOLMAN_URL"
echo "Found $COUNT spools to delete."

if [ "$DRY_RUN" = true ]; then
  echo "Dry run: would delete these spool IDs:"
  printf '%s\n' "$IDS"
  exit 0
fi

echo "This is destructive. Type DELETE ALL to continue:"
read -r confirmation
if [ "$confirmation" != "DELETE ALL" ]; then
  echo "Aborting."
  exit 0
fi

echo "Type the target URL exactly to confirm:"
read -r url_confirmation
if [ "${url_confirmation%/}" != "$SPOOLMAN_URL" ]; then
  echo "Aborting: URL confirmation did not match."
  exit 0
fi

for id in $IDS; do
  echo "Deleting spool with ID: $id"
  curl --fail --silent --show-error -X DELETE "$API_URL/$id" >/dev/null
done

echo "Deleted $COUNT spools."
