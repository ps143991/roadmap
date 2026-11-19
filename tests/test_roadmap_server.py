"""Exercise file saves against an isolated HTTP server and temporary data."""

import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import roadmap_server as roadmap


class RoadmapSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="roadmap-server-test-")
        self.original_paths = roadmap.ROOT, roadmap.DATA_FILE, roadmap.BACKUP_FILE
        roadmap.ROOT = Path(self.temp.name)
        roadmap.DATA_FILE = roadmap.ROOT / "roadmap_data.json"
        roadmap.BACKUP_FILE = roadmap.ROOT / "roadmap_data.backup.json"
        roadmap.DATA_FILE.write_text('{"name": "Original"}\n')
        roadmap.SAVE_REVISIONS.clear()
        self.server = roadmap.ThreadingHTTPServer(("127.0.0.1", 0), roadmap.RoadmapHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        roadmap.ROOT, roadmap.DATA_FILE, roadmap.BACKUP_FILE = self.original_paths
        self.temp.cleanup()

    def save(self, data, query=""):
        request = Request(self.url + "/api/roadmap" + query, json.dumps(data).encode(), {"Content-Type": "application/json"})
        with urlopen(request) as response:
            return json.load(response)

    def test_save_and_backup_and_no_repeated_request_logs(self):
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            with urlopen(self.url + "/api/roadmap") as response:
                self.assertEqual(json.load(response), {"name": "Original"})
            self.assertTrue(self.save({"name": "Edited"})["ok"])
        self.assertEqual(logs.getvalue(), "")
        self.assertEqual(json.loads(roadmap.DATA_FILE.read_text()), {"name": "Edited"})
        self.assertEqual(json.loads(roadmap.BACKUP_FILE.read_text()), {"name": "Original"})
        self.save({"name": "Edited"})
        self.assertEqual(json.loads(roadmap.BACKUP_FILE.read_text()), {"name": "Original"})

    def test_late_request_cannot_overwrite_newer_close_time_save(self):
        self.save({"notes": "Last edit before close"}, "?session=test&revision=3")
        self.save({"notes": "Earlier edit"}, "?session=test&revision=2")
        self.assertEqual(json.loads(roadmap.DATA_FILE.read_text())["notes"], "Last edit before close")
        self.save({"notes": "Edit after relaunch"}, "?session=next&revision=1")
        self.assertEqual(json.loads(roadmap.DATA_FILE.read_text())["notes"], "Edit after relaunch")

    def test_invalid_payload_preserves_data(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(HTTPError) as error:
                self.save(["invalid"])
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(json.loads(roadmap.DATA_FILE.read_text()), {"name": "Original"})

    def test_user_data_and_server_files_are_not_static_downloads(self):
        (roadmap.ROOT / 'roadmap_server.py').write_text('not a public static asset')
        with contextlib.redirect_stderr(io.StringIO()):
            for path in ['/roadmap_data.json', '/roadmap_data.backup.json', '/roadmap_server.py', '/.git/config', '/vendor/../roadmap_server.py']:
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.url + path)
                self.assertEqual(error.exception.code, 404)

    def test_saves_write_to_the_user_folder_outside_app_sources(self):
        app_root = roadmap.ROOT
        user_data = app_root / 'user-data'
        user_data.mkdir()
        roadmap.DATA_FILE = user_data / 'roadmap_data.json'
        roadmap.BACKUP_FILE = user_data / 'roadmap_data.backup.json'
        roadmap.DATA_FILE.write_text('{"name":"User original"}\n')
        source_before = (app_root / 'roadmap_data.json').read_bytes()
        self.save({'name':'User edited'})
        self.assertEqual(json.loads(roadmap.DATA_FILE.read_text())['name'], 'User edited')
        self.assertEqual(json.loads(roadmap.BACKUP_FILE.read_text())['name'], 'User original')
        self.assertEqual((app_root / 'roadmap_data.json').read_bytes(), source_before)


if __name__ == "__main__":
    unittest.main()
