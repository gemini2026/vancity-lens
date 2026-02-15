#!/bin/sh
set -eu

# Replace build-time placeholder with runtime env var in all JS files
if [ -n "${NEXT_PUBLIC_MAPBOX_TOKEN:-}" ]; then
  # Sanitise token: allow only base64url-safe chars + dots to prevent sed injection
  if echo "$NEXT_PUBLIC_MAPBOX_TOKEN" | grep -qE '^pk\.[a-zA-Z0-9._-]+=*$'; then
    # Escape sed special characters in the token value for safety
    ESCAPED_TOKEN=$(printf '%s\n' "$NEXT_PUBLIC_MAPBOX_TOKEN" | sed 's/[&/\|]/\\&/g')
    find /app/.next \( -name '*.js' -o -name '*.html' -o -name '*.rsc' \) -exec sed -i "s|__MAPBOX_TOKEN_PLACEHOLDER__|${ESCAPED_TOKEN}|g" {} +

    # Verify replacement actually occurred
    remaining=$(grep -rl '__MAPBOX_TOKEN_PLACEHOLDER__' /app/.next/ 2>/dev/null | head -1 || true)
    if [ -n "$remaining" ]; then
      echo "[entrypoint] ERROR: Placeholder still found after replacement in: $remaining" >&2
      exit 1
    fi
    echo "[entrypoint] Mapbox token injected."
  else
    echo "[entrypoint] WARNING: NEXT_PUBLIC_MAPBOX_TOKEN has unexpected format (expected 'pk.<base64url>'). Got prefix: '$(echo "$NEXT_PUBLIC_MAPBOX_TOKEN" | cut -c1-4)...'. Skipping replacement." >&2
  fi
else
  echo "[entrypoint] WARNING: NEXT_PUBLIC_MAPBOX_TOKEN is not set; map features will not work." >&2
fi

exec node server.js
