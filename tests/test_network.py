"""Check production request policy independently of Windows browser launch."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from playwright.sync_api import sync_playwright
from screenshotbot import collector as c
from test_capture import tripwire


class RequestPolicyTests(TestCase):
    def test_renderer_rejects_external_source_before_launch(self):
        with self.assertRaises(c.CaptureError) as caught:
            c.render("match-stats", "panel", "https://example.invalid/match-stats.html")
        self.assertEqual(caught.exception.code, "network_denied")

    def test_disallowed_requests_never_fetch(self):
        url = "http://127.0.0.1:31001/match-stats.html"
        for target, method, kind in [
                ("http://127.0.0.1:31002/match-stats.html", "GET", "document"),
                (url, "GET", "image"), (url, "POST", "document"), (url + "?source=x", "GET", "document")]:
            with self.subTest(target=target, kind=kind, method=method):
                route = MagicMock()
                route.request = SimpleNamespace(url=target, method=method, resource_type=kind)
                failures = []
                c.allow_document(route, url=url, failures=failures)
                route.fetch.assert_not_called()
                route.abort.assert_called_once()
                self.assertEqual(failures[0][0], "network_denied")

    def test_redirect_response_never_reaches_second_origin(self):
        with tripwire() as (destination, hits):
            def redirect(handler):
                handler.send_response(302)
                handler.send_header("Location", destination)
                handler.end_headers()
            with patch.object(c.FixtureHandler, "do_GET", redirect), c.fixture_server("match-stats") as url:
                with sync_playwright() as pw:
                    api = pw.request.new_context()
                    try:
                        route = MagicMock()
                        route.request = SimpleNamespace(url=url, method="GET", resource_type="document")
                        route.fetch.side_effect = lambda **kwargs: api.get(url, **kwargs)
                        failures = []
                        c.allow_document(route, url=url, failures=failures)
                        self.assertEqual(failures[0][0], "redirect_denied")
                        route.fulfill.assert_not_called()
                        route.abort.assert_called_once()
                    finally:
                        api.dispose()
            self.assertEqual(hits, [])
