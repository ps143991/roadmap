#!/usr/bin/env python3
"""Install a private copy of the program and its application-menu shortcut."""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from roadmap_packaging import copy_application, desktop_entry
from roadmap_storage import default_data_directory, xdg_directory

ROOT = Path(__file__).resolve().parent


def check_runtime():
    import gi
    gi.require_version('Gtk', '3.0')
    try:
        gi.require_version('WebKit2', '4.1')
    except ValueError:
        gi.require_version('WebKit2', '4.0')
    from gi.repository import Gtk, WebKit2


def install(desktop=False):
    check_runtime()
    data_home = xdg_directory('XDG_DATA_HOME', '.local/share')
    app_home = data_home / 'thesis-roadmap'
    destination = app_home / 'app'
    app_home.mkdir(parents=True, exist_ok=True)
    if ROOT != destination.resolve():
        with tempfile.TemporaryDirectory(prefix='.install-', dir=app_home) as staging:
            staging = Path(staging)
            prepared, previous = staging / 'app', staging / 'previous'
            copy_application(ROOT, prepared)
            if destination.exists():
                destination.rename(previous)
            try:
                prepared.rename(destination)
            except OSError:
                if previous.exists():
                    previous.rename(destination)
                raise
    launchers = data_home / 'applications'
    launchers.mkdir(parents=True, exist_ok=True)
    launcher = launchers / 'org.thesisroadmap.App.desktop'
    launcher.write_text(desktop_entry(destination / 'start_roadmap.sh', destination / 'roadmap.svg'))
    launcher.chmod(0o644)
    if desktop:
        desktop_path = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
        shortcut = Path(desktop_path) / launcher.name
        shutil.copy2(launcher, shortcut)
        shortcut.chmod(0o755)
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(launchers)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Installed Thesis Roadmap. Open it from your applications menu.')
    print(f'Program: {destination}')
    print(f'Your work: {default_data_directory()} (created on first launch)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true', help='Also put a shortcut on your Desktop')
    options = parser.parse_args()
    try:
        install(options.desktop)
    except (ImportError, ValueError) as error:
        raise SystemExit(f'Desktop dependencies are missing: {error}\nRun: bash install.sh --install-deps')


if __name__ == '__main__':
    main()
