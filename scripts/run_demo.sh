#!/usr/bin/env bash
# Verify the frozen demo files against CLAUDE.md, run the sanity checks, then start the app.
# Usage on the server, from the project folder:  bash scripts/run_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
export PYTHONIOENCODING=utf-8

# Secrets live in deploy.env (chmod 600, never committed). Loaded only if present.
if [ -f deploy.env ]; then set -a; . ./deploy.env; set +a; fi
export APP_HOST="${APP_HOST:-127.0.0.1}" APP_PORT="${APP_PORT:-8501}"

failed=0
pattern='^| `\(data/[^`]*\)`.*`\([0-9A-Fa-f]\{64\}\)`.*'
while IFS= read -r line; do
  file=$(printf '%s\n' "$line" | sed -n "s#$pattern#\1#p")
  expected=$(printf '%s\n' "$line" | sed -n "s#$pattern#\2#p" | tr 'A-F' 'a-f')
  [ -z "$file" ] && continue
  if [ ! -f "$file" ]; then
    echo "MISSING  $file"; failed=1
  elif [ "$(sha256sum "$file" | cut -d' ' -f1)" = "$expected" ]; then
    echo "OK       $file"
  else
    echo "CHANGED  $file (does not match CLAUDE.md)"; failed=1
  fi
done < <(grep '^| `data/' CLAUDE.md)

if [ "$failed" -ne 0 ]; then
  echo "Stopped: fix the files above before the demo."
  exit 1
fi

"$PYTHON" scripts/check_data.py

[ -z "${IBM_API_KEY:-}${IBM_ACCESS_TOKEN:-}" ] && echo "Note: no IBM credentials set, so Granite summaries are off."
[ -z "${DASHBOARD_PASSWORD:-}" ] && echo "Note: DASHBOARD_PASSWORD is not set, so the dashboard has no login."

echo ""
echo "Demo running at http://$APP_HOST:$APP_PORT (Ctrl+C to stop)"
exec "$PYTHON" -m app.main
