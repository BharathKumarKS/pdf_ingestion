#!/usr/bin/env bash
# Start the Phoenix observability server on the ports this machine actually has.
#
# Why the defaults fail here:
#   6006  — taken by another local app, which is why .env uses 6007
#   4317  — held by Docker Desktop; if gRPC cannot bind, Phoenix exits entirely with
#           "Failed to bind to address [::]:4317" and nothing is traced at all.
#
# The app reads PHOENIX_ENDPOINT from .env (http://localhost:6007), so serve there.
#
# Usage:
#   ./scripts/start_phoenix.sh          # foreground (Ctrl-C to stop)
#   ./scripts/start_phoenix.sh --bg     # background, logs to $PHOENIX_LOG
#
# After starting, the app's sidebar should read "🔭 Phoenix traces — active".
# Verify traces are actually persisting (a 200 from /v1/traces does NOT prove it —
# a malformed ~/.phoenix/phoenix.db accepts the POST and drops the span):
#   curl -s "http://localhost:6007/v1/projects/synapse-learning/spans?limit=5"
set -euo pipefail

PHOENIX_PORT="${PHOENIX_PORT:-6007}"
PHOENIX_GRPC_PORT="${PHOENIX_GRPC_PORT:-4319}"
export PHOENIX_PORT PHOENIX_GRPC_PORT

if ! command -v phoenix >/dev/null 2>&1; then
  echo "phoenix CLI not found. Install it with:  uv tool install arize-phoenix" >&2
  exit 1
fi

echo "Phoenix UI     : http://localhost:${PHOENIX_PORT}"
echo "Phoenix OTLP   : http://localhost:${PHOENIX_PORT}/v1/traces  (gRPC ${PHOENIX_GRPC_PORT})"

if [[ "${1:-}" == "--bg" ]]; then
  LOG="${PHOENIX_LOG:-${TMPDIR:-/tmp}/phoenix.log}"
  nohup phoenix serve >"$LOG" 2>&1 &
  echo "started (pid $!) → ${LOG}"
  echo "stop with:  kill $!"
else
  exec phoenix serve
fi