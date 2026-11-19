#!/bin/bash
set -eu
exec "${THESIS_ROADMAP_PYTHON:-/usr/bin/python3}" - <<'PY'
import shutil
from pathlib import Path
import os

value = os.environ.get('XDG_DATA_HOME', '')
base = Path(value) if value and Path(value).is_absolute() else Path.home() / '.local/share'
app = base / 'thesis-roadmap' / 'app'
launcher = base / 'applications' / 'org.thesisroadmap.App.desktop'
if app.exists():
    shutil.rmtree(app)
launcher.unlink(missing_ok=True)
print('Removed the per-user installation and menu shortcut.')
print(f'Your work is kept in: {base / "thesis-roadmap" / "data"}')
PY
