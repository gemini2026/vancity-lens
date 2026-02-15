#!/bin/sh
set -e

# Replace build-time placeholder with runtime env var in all JS files
if [ -n "$NEXT_PUBLIC_MAPBOX_TOKEN" ]; then
  # Validate Mapbox public token format before sed substitution
  if echo "$NEXT_PUBLIC_MAPBOX_TOKEN" | grep -qE '^pk\.[a-zA-Z0-9_-]+$'; then
    find /app/.next -name '*.js' -exec sed -i "s|__MAPBOX_TOKEN_PLACEHOLDER__|${NEXT_PUBLIC_MAPBOX_TOKEN}|g" {} +
    echo "[entrypoint] Mapbox token injected."
  else
    echo "[entrypoint] WARNING: NEXT_PUBLIC_MAPBOX_TOKEN has unexpected format, skipping replacement." >&2
  fi
else
  echo "[entrypoint] WARNING: NEXT_PUBLIC_MAPBOX_TOKEN is not set; map features will not work." >&2
fi

exec node server.js
