# Capture and receipt contract

The CLI accepts a fixture name and a mode. It has no URL, file path, external profile, or custom locator input. The two immutable-at-runtime fixture definitions are under tests/fixtures/synthetic/. The match page identifies both sides, regulation period and fixture. The league page identifies its season, table basis and six column headings. Both use embedded CSS and installed Windows fonts.

The collector holds a project-wide Windows byte-range lock during a job. An ephemeral HTTP server listens on 127.0.0.1 and serves one exact resource with an exact Host header. The selected Chromium-based browser has JavaScript disabled, service workers blocked, and a non-forwarding loopback proxy for unrouted traffic. Playwright interception admits only an exact document GET. The handler obtains the response with max_redirects=0 and rejects all redirects and non-200 responses. Other origins and all subresources are denied. A rejected browser request makes the capture fail. No external test destination is needed. This is a boundary for owned fixtures, not a general-purpose browsing service.

After the page load and font check, the collector requires a visible statistics panel and named identity anchors with expected text and bounding boxes inside the panel. It captures either the panel or the full page. Context, browser, driver, temporary profile and server are released on exit. Each operation has a timeout. A normal job publishes its PNG and receipt by renaming the staging directory on the same volume. An interruption before rename can leave a hidden-by-convention .partial folder; consumers must read only published capture-ID directories. Keep original bytes and receipts together. A new acquisition has a new ID even if its bytes match an earlier capture.

## Receipt v1

| Field | Meaning |
|---|---|
| receipt_version, status | Integer 1 and success in a published pair. Failures are reported separately. |
| capture_id, fixture_id | UUID4 in hexadecimal and the selected bundled fixture. |
| capture_mode, locator | panel with #stats-panel, or full-page with document. |
| captured_at | UTC timestamp recorded immediately after capture, with a Z suffix. |
| source_url | Ephemeral local URL used in this acquisition. The server closes after the job. |
| width, height | Original PNG raster dimensions in pixels, read from IHDR. |
| viewport, device_scale | CSS viewport width/height (1280 by 800) and scale factor 1. |
| browser_channel, browser_version, capture_profile | Selected channel (chromium or msedge), running browser version and synthetic-desktop-v1. Uses light theme, en-US and UTC. |
| image, sha256 | Relative basename original.png and lowercase SHA-256 over the exact stored bytes. |

Local font versions can affect rendered pixels. Repeated captures have separate identifiers and times. SHA-256 supports integrity comparison, not a trusted timestamp. This Windows prototype expects an editable checkout with bundled HTML available. Source rights, OCR, SQLite and a generic URL capture interface are outside SB-1.

## Explicit browser selection

SB-1F adds --channel msedge using the installed Edge distribution. Omit --channel to preserve chromium selection. No executable path is hardcoded. Both use the same capture, receipt publication and isolation code. Receipts gain browser_channel as an additive v1 field. Consumers should tolerate this documented additional field. Edge version is observed at runtime; installed Edge is not pinned by the project. The recovery trial used 157.0.4341.46.

## Accepted local target

The owner accepts installed Edge for the Windows-local synthetic prototype. Select --channel msedge explicitly; the default remains chromium. The recorded fresh Python/project setup reused the same host and installed Edge, passed all 21 tests and four additional capture commands, and does not establish fresh Windows/Edge or different-PC reproduction. The original Chromium signing-policy launch denial remains historical evidence. No policy bypass is authorized. See [the project README](../README.md) for setup, acceptance limits and licensing.
