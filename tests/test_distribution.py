"""Data isolation, per-user installs, and shareable archive checks."""

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_release
from roadmap_packaging import copy_application
from roadmap_storage import TEMPLATE_FILE, default_data_directory, initialize_data


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='roadmap-storage-check-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_first_launch_starts_from_generic_template_and_preserves_it(self):
        original = TEMPLATE_FILE.read_bytes()
        data = initialize_data(self.root / 'profile')
        self.assertEqual((data / 'roadmap_data.json').read_bytes(), original)
        self.assertEqual(TEMPLATE_FILE.read_bytes(), original)
        document = json.loads(original)
        self.assertEqual(document['name'], 'My Thesis')
        self.assertEqual(document['history'], [])
        self.assertEqual(len(document['children']), 6)
        self.assertEqual((data / 'roadmap_data.json').stat().st_mode & 0o777, 0o600)

    def test_reinitialization_preserves_user_notes_and_backup(self):
        data = initialize_data(self.root / 'profile')
        current, backup = data / 'roadmap_data.json', data / 'roadmap_data.backup.json'
        current.write_text('{"name":"My work","notes":"Keep this"}\n')
        backup.write_text('{"notes":"Previous version"}\n')
        hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in [current, backup]]
        initialize_data(data)
        self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in [current, backup]], hashes)

    def test_profiles_are_independent(self):
        first = initialize_data(self.root / 'first')
        second = initialize_data(self.root / 'second')
        (first / 'roadmap_data.json').write_text('{"name":"First only"}')
        self.assertEqual(json.loads((second / 'roadmap_data.json').read_text())['name'], 'My Thesis')

    def test_data_home_and_explicit_override(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'user data'), 'THESIS_ROADMAP_DATA_DIR': ''}):
            self.assertEqual(default_data_directory(), self.root / 'user data/thesis-roadmap/data')
        with patch.dict(os.environ, {'THESIS_ROADMAP_DATA_DIR': str(self.root / 'portable')}):
            self.assertEqual(default_data_directory(), self.root / 'portable')


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='roadmap-install-check-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_copy_allowlist_excludes_personal_data_and_history(self):
        source, destination = self.root / 'source', self.root / 'payload'
        copy_application(ROOT, source)
        (source / 'roadmap_data.json').write_text('{"private":"do not ship"}')
        (source / 'roadmap_data.backup.json').write_text('{"private":"old notes"}')
        (source / '.git').mkdir()
        (source / '.git/config').write_text('private history')
        copy_application(source, destination)
        self.assertFalse((destination / 'roadmap_data.json').exists())
        self.assertFalse((destination / 'roadmap_data.backup.json').exists())
        self.assertFalse((destination / '.git').exists())
        self.assertTrue((destination / 'examples/starter-roadmap.json').is_file())
        self.assertTrue((destination / 'vendor/katex/katex.min.js').is_file())

    def test_user_install_and_update_preserve_data_and_create_shortcut(self):
        env = dict(os.environ, XDG_DATA_HOME=str(self.root / 'data with spaces'), XDG_CACHE_HOME=str(self.root / 'cache'), THESIS_ROADMAP_DATA_DIR='', THESIS_ROADMAP_PYTHON=sys.executable)
        command = ['bash', str(ROOT / 'install.sh')]
        subprocess.run(command, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data_home = Path(env['XDG_DATA_HOME'])
        app = data_home / 'thesis-roadmap/app'
        launcher = data_home / 'applications/org.thesisroadmap.App.desktop'
        self.assertTrue((app / 'roadmap_app.py').is_file())
        self.assertIn('Terminal=false', launcher.read_text())
        self.assertIn(str(app / 'start_roadmap.sh'), launcher.read_text())
        subprocess.run(['desktop-file-validate', str(launcher)], check=True)
        data = initialize_data(data_home / 'thesis-roadmap/data')
        current, backup = data / 'roadmap_data.json', data / 'roadmap_data.backup.json'
        current.write_text('{"name":"Keep user work"}\n')
        backup.write_text('{"notes":"Keep backup"}\n')
        original = current.read_bytes(), backup.read_bytes()
        subprocess.run(command, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual((current.read_bytes(), backup.read_bytes()), original)
        self.assertFalse((app / 'roadmap_data.json').exists())
        result = subprocess.run([str(app / 'start_roadmap.sh'), '--server', '--help'], env=env, check=True, capture_output=True, text=True)
        self.assertIn('--data-dir', result.stdout)

    def test_release_contains_installer_and_generic_data_only(self):
        archive = build_release.build(self.root / 'dist')
        with tarfile.open(archive) as stream:
            files = [entry.name for entry in stream.getmembers() if entry.isfile()]
            self.assertTrue(any(name.endswith('/install.sh') for name in files))
            self.assertTrue(any(name.endswith('/examples/starter-roadmap.json') for name in files))
            self.assertFalse(any('/.git/' in name or name.endswith('/roadmap_data.json') or name.endswith('/roadmap_data.backup.json') for name in files))
            self.assertFalse(any('__pycache__' in name or name.endswith('.pyc') for name in files))
        checksum = archive.with_name(archive.name + '.sha256').read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
