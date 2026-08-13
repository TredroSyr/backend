#!/bin/sh
# Thin wrapper kept for convenience; the image entrypoint uses wait_for_db.py.
set -e
exec python /app/docker/wait_for_db.py "$@"
