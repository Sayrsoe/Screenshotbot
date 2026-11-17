"""Capture a bundled HTML fixture and publish its original PNG and receipt."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import msvcrt
import os
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import Error, TimeoutError as BrowserTimeout, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "tasks/SB-1/scratch"
FIXTURES = ROOT / "tests/fixtures/synthetic"
VIEWPORT = {"width": 1280, "height": 800}
TIMEOUT_MS = 8000
PANEL = "#stats-panel"
PROFILE = "synthetic-desktop-v1"
ANCHORS = {
    "match-stats": {"#competition": "Glasswater Cup", "#identity": "Cinder Quay vs Lantern Vale",
                    "#fixture": "GC-032", "#score": "Final regulation score", "#home": "Home · Cinder Quay",
                    "#away": "Away · Lantern Vale", "thead th:first-child": "Statistic"},
    "league-xg": {"#competition": "Rainspire League", "#identity": "League expected goals table",
                  "#basis": "Season totals", "#col-0": "Team", "#col-1": "Played", "#col-2": "xG",
                  "#col-3": "xGA", "#col-4": "xPts", "#col-5": "Actual points"},
}
MODES = ("panel", "full-page")
CHANNELS = ("chromium", "msedge")


class CaptureError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class FixtureHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, fixture, document, **kwargs):
        self.fixture = fixture
        self.document = document
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403)
            return
        if self.path != f"/{self.fixture}.html":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.document)))
        self.send_header("X-DNS-Prefetch-Control", "off")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(self.document)

    def log_message(self, *_):
        pass


@contextmanager
def fixture_server(fixture):
    if fixture not in ANCHORS:
        raise CaptureError('invalid_input', 'Unknown fixture.')
    document = (FIXTURES / f"{fixture}.html").read_bytes()
    handler = partial(FixtureHandler, fixture=fixture, document=document)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/{fixture}.html"
        finally:
            server.shutdown()
            thread.join()


@contextmanager
def job_lock():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with (SCRATCH / "collector.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise CaptureError("busy", "Another collector has the project lock.") from exc
        yield  # Closing the file releases this Windows byte-range lock.


def allow_document(route, *, url, failures):
    request = route.request
    if request.url != url or request.method != "GET" or request.resource_type != "document":
        failures.append(("network_denied", f"Unapproved request: {request.resource_type}"))
        route.abort()
        return
    response = None
    try:
        # Read only the exact loopback resource. Never let Chromium follow a redirect.
        response = route.fetch(max_redirects=0, timeout=TIMEOUT_MS)
        if response.status != 200:
            code = "redirect_denied" if 300 <= response.status < 400 else "source_failed"
            failures.append((code, f"Fixture server returned HTTP {response.status}."))
            route.abort()
        else:
            route.fulfill(response=response)
    except Error as exc:
        code = "timeout" if "timeout" in str(exc).lower() else "source_failed"
        failures.append((code, "Local fixture response failed."))
        route.abort()
    finally:
        if response:
            response.dispose()

def render(fixture, mode, url, *, channel="chromium"):
    if channel not in CHANNELS:
        raise CaptureError("invalid_input", "Unsupported browser channel.")
    address = urlsplit(url)
    if (fixture not in ANCHORS or address.scheme != "http" or not address.port or
            url != f"http://127.0.0.1:{address.port}/{fixture}.html"):
        raise CaptureError("network_denied", "Expected the dedicated loopback fixture URL.")
    failures = []

    with ExitStack() as stack:
        # Driver and browser inherit these process-local locations; restore on return.
        original = {name: os.environ.get(name) for name in ("PLAYWRIGHT_BROWSERS_PATH", "TEMP", "TMP")}
        tmp = SCRATCH / "tmp"
        tmp.mkdir(exist_ok=True)
        tmp = Path(stack.enter_context(TemporaryDirectory(dir=tmp, prefix='job-')))
        for name, value in original.items():
            if value is None:
                stack.callback(os.environ.pop, name, None)
            else:
                stack.callback(os.environ.__setitem__, name, value)
        os.environ.update(PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".browsers"), TEMP=str(tmp), TMP=str(tmp))
        pw = stack.enter_context(sync_playwright())
        # All unhandled browser traffic goes to the loopback fixture server as a
        # non-forwarding proxy. Only the route handler above performs a direct GET.
        proxy = url.rsplit("/", 1)[0]
        browser = pw.chromium.launch(channel=channel, headless=True, timeout=15000, args=[
            f"--proxy-server={proxy}", "--proxy-bypass-list=<-loopback>",
            "--host-resolver-rules=MAP * ~NOTFOUND", "--disable-background-networking",
        ])
        stack.callback(browser.close)
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="en-US",
                                      timezone_id="UTC", color_scheme="light", service_workers="block",
                                      java_script_enabled=False, accept_downloads=False)
        stack.callback(context.close)
        context.set_default_timeout(TIMEOUT_MS)
        context.route("**/*", partial(allow_document, url=url, failures=failures))
        page = context.new_page()
        try:
            page.goto(url, wait_until="load", timeout=TIMEOUT_MS)
        except Error:
            if failures:
                raise CaptureError(*failures[0])
            raise
        if failures:
            raise CaptureError(*failures[0])
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=TIMEOUT_MS)
        panel = page.locator(PANEL)
        if panel.count() != 1 or not panel.is_visible():
            raise CaptureError("missing_panel", "Expected one visible statistics panel.")
        bounds = panel.bounding_box()
        for selector, text in ANCHORS[fixture].items():
            header = panel.locator(selector)
            if header.count() != 1 or not header.is_visible() or text not in header.inner_text():
                raise CaptureError("missing_header", f"Required header is missing: {selector}")
            box = header.bounding_box()
            if not all(bounds[axis] <= box[axis] and
                       box[axis] + box[size] <= bounds[axis] + bounds[size]
                       for axis, size in (("x", "width"), ("y", "height"))):
                raise CaptureError("clipped_header", f"Header extends beyond panel: {selector}")
        if mode == "panel":
            png = panel.screenshot(type="png", animations="disabled")
        else:
            png = page.screenshot(type="png", full_page=True, animations="disabled")
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if failures:
            raise CaptureError(*failures[0])
        return png, timestamp, browser.version


def capture(fixture, mode, output=None, *, channel="chromium"):
    if fixture not in ANCHORS or mode not in MODES or channel not in CHANNELS:
        raise CaptureError("invalid_input", "Select a bundled fixture and supported capture mode.")
    output = ROOT / "captures" if output is None else Path(output)
    try:
        with job_lock(), fixture_server(fixture) as url:
            png, captured_at, browser_version = render(fixture, mode, url, channel=channel)
            capture_id = uuid4().hex
            if png[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
                raise CaptureError("invalid_png", "Chromium did not return an original PNG.")
            width, height = struct.unpack(">II", png[16:24])
            receipt = {
                "receipt_version": 1, "capture_id": capture_id, "fixture_id": fixture,
                "capture_mode": mode, "captured_at": captured_at, "source_url": url,
                "width": width, "height": height, "viewport": VIEWPORT, "device_scale": 1,
                "browser_version": browser_version, "browser_channel": channel, "capture_profile": PROFILE,
                "sha256": sha256(png).hexdigest(), "status": "success",
                "locator": PANEL if mode == "panel" else "document", "image": "original.png",
            }
            output.mkdir(parents=True, exist_ok=True)
            stage = output / f".{capture_id}.partial"
            stage.mkdir()
            try:
                (stage / "original.png").write_bytes(png)
                (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                final = output / capture_id
                stage.rename(final)
                return final
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
    except BrowserTimeout as exc:
        raise CaptureError("timeout", "Timed out waiting for the local page or browser.") from exc
    except Error as exc:
        raise CaptureError("browser_failed", str(exc).splitlines()[0]) from exc
    except OSError as exc:
        raise CaptureError("io_failed", str(exc)) from exc
