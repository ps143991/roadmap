"""Explicit application payload: personal data and Git history are never copied."""

import shutil
from pathlib import Path

APPLICATION_FILES = ('VERSION', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'roadmap_storage.py', 'roadmap_server.py', 'roadmap_app.py', 'roadmap_features.js', 'notes_editor.js', 'roadmap_these.html', 'gantt.html', 'roadmap.svg', 'roadmap.png', 'start_roadmap.sh')
APPLICATION_DIRECTORIES = ('examples', 'vendor')
DISTRIBUTION_FILES = ('README.md', 'install.sh', 'install_app.py', 'uninstall.sh', 'roadmap_packaging.py', 'build_release.py')


def copy_application(source, destination):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in APPLICATION_FILES:
        shutil.copy2(source / name, destination / name)
    for name in APPLICATION_DIRECTORIES:
        shutil.copytree(source / name, destination / name)


def desktop_entry(command, icon):
    escaped = str(command).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    return f'''[Desktop Entry]
Type=Application
Name=Thesis Roadmap
Comment=Plan a thesis with an interactive roadmap, notes, and autosave
Exec="{escaped}"
Icon={icon}
Terminal=false
Categories=Office;ProjectManagement;
StartupNotify=true
StartupWMClass=thesis-roadmap
'''
