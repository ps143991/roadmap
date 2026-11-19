#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"

if [ "${1:-}" = "--install-deps" ]; then
    shift
    if ! command -v apt-get >/dev/null 2>&1; then
        echo 'Automatic dependency setup supports Debian/Ubuntu. See README.md for the required GTK/WebKit packages.' >&2
        exit 1
    fi
    webkit_package=gir1.2-webkit2-4.1
    if [ -r /etc/os-release ]; then
        . /etc/os-release
        if [ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 22.04 ]; then
            webkit_package=gir1.2-webkit2-4.0
        fi
    fi
    sudo apt-get update
    sudo apt-get install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 "$webkit_package"
fi
exec "${THESIS_ROADMAP_PYTHON:-/usr/bin/python3}" install_app.py "$@"
