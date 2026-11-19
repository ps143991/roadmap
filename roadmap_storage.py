"""Keep application files and each user's thesis work in separate directories."""

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
TEMPLATE_FILE = APP_ROOT / 'examples' / 'starter-roadmap.json'


def xdg_directory(variable, fallback):
    value = os.environ.get(variable, '')
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def default_data_directory():
    override = os.environ.get('THESIS_ROADMAP_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'ThesisRoadmap' / 'data'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'ThesisRoadmap' / 'data'
    return xdg_directory('XDG_DATA_HOME', '.local/share') / 'thesis-roadmap' / 'data'


def initialize_data(directory=None):
    directory = Path(directory).expanduser().resolve() if directory else default_data_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / 'roadmap_data.json'
    if not destination.exists():
        starter = TEMPLATE_FILE.read_bytes()
        try:
            with destination.open('xb') as stream:
                os.chmod(destination, 0o600)
                stream.write(starter)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    return directory
