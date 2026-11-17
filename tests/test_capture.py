"""SB-1 acceptance tests. Network tripwires use a second owned loopback port."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from functools import partial
from pathlib import Path
import socket
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import zlib

from screenshotbot import collector as c
from playwright.sync_api import BrowserType

TEST_CHANNEL = os.environ.get("SCREENSHOTBOT_TEST_CHANNEL", "chromium")


def cli(*args):
    return subprocess.run([sys.executable, "-m", "screenshotbot", "capture", "--channel", TEST_CHANNEL, *args],
                          text=True, capture_output=True, timeout=45)


def read_png(data):
    """Check the signature, every CRC and the complete decompressed screenshot raster."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Bad PNG signature")
    pos = 8
    image_data = bytearray()
    width = height = channels = 0
    while pos < len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        payload = data[pos+8:pos+8+length]
        crc, = struct.unpack_from(">I", data, pos+8+length)
        if zlib.crc32(kind + payload) != crc:
            raise ValueError("Bad chunk CRC")
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if not (width and height and depth == 8 and (comp, filt, interlace) == (0, 0, 0)):
                raise ValueError("Unexpected screenshot format")
            channels = {2: 3, 6: 4}[color]
        if kind == b"IDAT":
            image_data.extend(payload)
        if kind == b"IEND":
            break
    if kind != b"IEND" or pos != len(data):
        raise ValueError("Incomplete or trailing PNG data")
    raster = zlib.decompress(image_data)
    stride = width * channels + 1
    if len(raster) != height * stride or any(f > 4 for f in raster[::stride]):
        raise ValueError("Invalid screenshot raster")
    return width, height


@contextmanager
def tripwire():
    hits = []

    class Observer(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_error(404)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Observer) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/forbidden", hits
        finally:
            server.shutdown()
            thread.join()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(c, "capture", wraps=partial(c.capture, channel=TEST_CHANNEL)))
        scratch = c.SCRATCH / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.output = Path(self.enterContext(TemporaryDirectory(dir=scratch)))
        self.tmp_before = set((c.SCRATCH / "tmp").glob("job-*"))

    def tearDown(self):
        self.assertEqual(self.tmp_before, set((c.SCRATCH / "tmp").glob("job-*")))

    def check_success(self, fixture, mode):
        result = c.capture(fixture, mode, self.output)
        self.assertEqual({p.name for p in result.iterdir()}, {"original.png", "receipt.json"})
        rec = json.loads((result / "receipt.json").read_text())
        png = (result / rec["image"]).read_bytes()
        self.assertEqual(rec["sha256"], sha256(png).hexdigest())
        self.assertEqual(read_png(png), (rec["width"], rec["height"]))
        self.assertEqual(datetime.fromisoformat(rec["captured_at"]).utcoffset(), timedelta(0))
        self.assertTrue(rec["captured_at"].endswith("Z"))
        self.assertEqual((rec["fixture_id"], rec["capture_mode"], rec["capture_profile"]),
                         (fixture, mode, "synthetic-desktop-v1"))
        self.assertEqual((rec["capture_id"], rec["status"], rec["device_scale"]), (result.name, "success", 1))
        self.assertEqual(rec["viewport"], {"width": 1280, "height": 800})
        self.assertEqual(rec["locator"], "#stats-panel" if mode == "panel" else "document")
        self.assertTrue(rec["browser_version"])
        self.assertEqual(rec["browser_channel"], TEST_CHANNEL)
        self.assertEqual(rec["width"], 1040 if mode == "panel" else 1280)
        address = urlsplit(rec["source_url"])
        self.assertEqual((address.hostname, address.path), ("127.0.0.1", f"/{fixture}.html"))
        with self.assertRaises(OSError):
            socket.create_connection((address.hostname, address.port), timeout=.5)
        return result.name

    def test_match_full(self):
        self.check_success("match-stats", "full-page")

    def test_match_panel(self):
        self.check_success("match-stats", "panel")

    def test_table_full(self):
        self.check_success("league-xg", "full-page")

    def test_table_panel(self):
        self.check_success("league-xg", "panel")

    def test_repeated_capture(self):
        self.assertNotEqual(self.check_success("match-stats", "panel"), self.check_success("match-stats", "panel"))

    def check_failure(self, expected):
        with self.assertRaises(c.CaptureError) as caught:
            c.capture("match-stats", "panel", self.output)
        self.assertEqual(caught.exception.code, expected, str(caught.exception))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_unknown_fixture(self):
        self.assertEqual(cli("--fixture", "unknown", "--mode", "panel").returncode, 2)

    def test_invalid_mode(self):
        self.assertEqual(cli("--fixture", "match-stats", "--mode", "crop").returncode, 2)

    def test_url_as_input(self):
        result = cli("--fixture", "match-stats", "--mode", "panel", "--url", "http://example.invalid/")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_host_and_path(self):
        with c.fixture_server("match-stats") as url:
            addr = urlsplit(url)
            for host, path, status in [(addr.netloc, addr.path, 200), ("wrong.invalid", addr.path, 403),
                                       (addr.netloc, "/other", 404)]:
                conn = HTTPConnection(addr.hostname, addr.port, timeout=2)
                try:
                    conn.request("GET", path, headers={"Host": host})
                    self.assertEqual(conn.getresponse().status, status)
                finally:
                    conn.close()
        with self.assertRaises(OSError):
            socket.create_connection((addr.hostname, addr.port), timeout=.5)

    def test_busy(self):
        with c.job_lock():
            result = cli("--fixture", "match-stats", "--mode", "panel")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "busy")

    def test_browser_failure(self):
        original_launch = BrowserType.launch

        def unavailable(browser_type, **kwargs):
            return original_launch(browser_type, **dict(kwargs, executable_path=str(self.output / "absent.exe")))

        with patch.object(BrowserType, "launch", unavailable):
            self.check_failure("browser_failed")

    @contextmanager
    def edited_document(self, document):
        with TemporaryDirectory(dir=c.SCRATCH / "tests") as directory:
            fixture_folder = Path(directory)
            (fixture_folder / "match-stats.html").write_text(document, encoding="utf-8")
            with patch.object(c, "FIXTURES", fixture_folder):
                yield

    def document(self):
        return (c.FIXTURES / "match-stats.html").read_text(encoding="utf-8")

    def test_missing_panel(self):
        with self.edited_document(self.document().replace('id="stats-panel"', 'id="absent"')):
            self.check_failure("missing_panel")

    def test_hidden_home_header(self):
        with self.edited_document(self.document().replace('id="home"', 'id="home" hidden')):
            self.check_failure("missing_header")

    def test_timeout(self):
        def slow_response(handler):
            time.sleep(1)
            handler.close_connection = True
        with patch.object(c.FixtureHandler, "do_GET", slow_response), patch.object(c, "TIMEOUT_MS", 350):
            self.check_failure("timeout")

    def test_off_origin_subresource(self):
        with tripwire() as (url, hits):
            with self.edited_document(self.document().replace("</body>", f'<img src="{url}"></body>')):
                self.check_failure("network_denied")
            self.assertEqual(hits, [])

    def test_off_origin_navigation(self):
        with tripwire() as (url, hits):
            with self.edited_document(self.document().replace("</body>", f'<iframe src="{url}"></iframe></body>')):
                self.check_failure("network_denied")
            self.assertEqual(hits, [])

    def test_off_origin_redirect(self):
        with tripwire() as (url, hits):
            def redirect(handler):
                handler.send_response(302)
                handler.send_header("Location", url)
                handler.end_headers()
            with patch.object(c.FixtureHandler, "do_GET", redirect):
                self.check_failure("redirect_denied")
            self.assertEqual(hits, [])

    def test_receipt_write_fails(self):
        # Exercise the real staging/rename path with a simulated filesystem failure.
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 10, 10)
        with patch.object(c, "render", return_value=(fake_png, "2032-01-01T00:00:00Z", "test")), \
             patch.object(Path, "write_text", side_effect=OSError("injected full disk")):
            self.check_failure("io_failed")
