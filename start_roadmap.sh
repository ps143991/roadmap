#!/bin/bash
set -eu

cd -- "$(dirname -- "$0")"
if [ "${1:-}" = "--server" ]; then
    shift
    exec "${THESIS_ROADMAP_PYTHON:-/usr/bin/python3}" roadmap_server.py "$@"
fi
exec "${THESIS_ROADMAP_PYTHON:-/usr/bin/python3}" roadmap_app.py "$@"
