#!/usr/bin/env python3
"""Vercel serverless function that wraps x2md.py for the web UI.

Expects a POST with JSON body: {"url": "https://x.com/handle/status/123"}
Returns JSON: {"markdown": "...", "meta": {...}}
"""

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Make the repository root importable so we can reuse x2md.py as a library.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import x2md

# Tuned for a serverless environment: generous enough to succeed, short enough
# that the worst-case chain (up to 4 providers) stays inside Vercel's limit.
_CLIENT_TIMEOUT = 15.0
_CLIENT_RETRIES = 1


def _convert(url: str) -> dict:
    """Run the same conversion the CLI uses and return a web-friendly payload."""
    target = x2md.parse_target(url)
    client = x2md.HttpClient(
        timeout=_CLIENT_TIMEOUT,
        max_retries=_CLIENT_RETRIES,
        user_agent="x2md-web/%s" % x2md.__version__,
    )
    providers = x2md.build_providers("auto", client, {})
    document, _errors = x2md.fetch_document(target, providers, client)
    markdown = x2md.render_document(document)

    return {
        "markdown": markdown,
        "meta": {
            "kind": document.kind,
            "id": document.status_id,
            "handle": document.author.handle or "",
            "name": document.author.name or "",
            "filename": x2md.default_filename(document),
            "source_url": document.source_url,
            "warnings": document.warnings,
            "provider": document.provider,
        },
    }


class handler(BaseHTTPRequestHandler):  # noqa: N801 — Vercel expects this name
    """Vercel-compatible request handler for /api/convert."""

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._send_error(405, "Method not allowed. Use POST /api/convert.")

    def do_POST(self) -> None:  # noqa: N802
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_length = 0

        body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return self._send_error(400, "Invalid JSON body.")
        except UnicodeDecodeError:
            return self._send_error(400, "Request body must be valid UTF-8.")

        url = data.get("url") if isinstance(data, dict) else None
        if not isinstance(url, str) or not url.strip():
            return self._send_error(400, "Missing or empty 'url' field.")

        url = url.strip()

        try:
            result = _convert(url)
        except x2md.InputError as exc:
            return self._send_error(400, str(exc))
        except x2md.NoProviderAvailable as exc:
            return self._send_error(502, str(exc))
        except Exception:  # pragma: no cover - defensive
            # Don't leak internals to the visitor; log enough for diagnostics.
            traceback.print_exc(file=sys.stderr)
            return self._send_error(500, "Internal server error.")

        self._send_json(200, result)
