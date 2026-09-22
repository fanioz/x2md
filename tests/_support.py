"""Shared helpers for the x2md test suite.

Stdlib only, and entirely offline: nothing here opens a socket. The CLI tests
install a fake HTTP layer so the full command path can be exercised against the
recorded fixtures without touching the network.
"""

import importlib.util
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
X2MD_DIR = HERE.parent
X2MD_PY = X2MD_DIR / "x2md.py"
FIXTURES = HERE / "fixtures"


def load_x2md():
    """Import ``x2md.py`` by path.

    The module is registered in ``sys.modules`` *before* execution because the
    dataclasses in it resolve their module via ``sys.modules`` at class-creation
    time. A pre-existing ``sys.modules['x2md']`` entry is only reused when it
    really is this file: the enclosing ``x2md/`` directory is importable as a PEP 420
    namespace package, and silently accepting that would produce confusing
    "module has no attribute" failures.
    """
    existing = sys.modules.get("x2md")
    if existing is not None and getattr(existing, "__file__", None) == str(X2MD_PY):
        return existing
    spec = importlib.util.spec_from_file_location("x2md", X2MD_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["x2md"] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "HttpClient"):  # pragma: no cover - defensive
        raise RuntimeError("failed to load x2md.py from %s" % X2MD_PY)
    return module


x2md = load_x2md()

ACTOR_LIB_PY = X2MD_DIR / "src" / "actor_lib.py"


def load_actor_lib():
    """Import ``src/actor_lib.py`` by path (same pattern as :func:`load_x2md`)."""
    existing = sys.modules.get("actor_lib")
    if existing is not None and getattr(existing, "__file__", None) == str(ACTOR_LIB_PY):
        return existing
    spec = importlib.util.spec_from_file_location("actor_lib", ACTOR_LIB_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["actor_lib"] = module
    spec.loader.exec_module(module)
    return module


def _install_network_guard():
    """Make any real socket use raise, proving the suite is offline.

    Opt-in via ``X2MD_TEST_BLOCK_NETWORK=1``. It is installed here rather than from
    an external ``sitecustomize`` because replacing ``socket.socket`` before
    unittest has bootstrapped discovery breaks the test loader itself; by this
    point the bootstrap is complete.
    """
    import socket

    class NetworkBlocked(RuntimeError):
        pass

    def blocked(*args, **kwargs):
        raise NetworkBlocked(
            "a test attempted real network access; the suite must run offline"
        )

    socket.socket = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    return NetworkBlocked


NETWORK_GUARD_ACTIVE = False
if os.environ.get("X2MD_TEST_BLOCK_NETWORK") == "1":
    _install_network_guard()
    NETWORK_GUARD_ACTIVE = True


def fixture_path(name):
    return FIXTURES / name


def load_fixture(name):
    with open(fixture_path(name), encoding="utf-8") as handle:
        return json.load(handle)


def load_fixture_text(name):
    return fixture_path(name).read_text(encoding="utf-8")


def parse_frontmatter(markdown):
    """Independent reader for the frontmatter subset x2md emits.

    Deliberately does not reuse x2md's writer: it re-reads the YAML block by
    splitting ``key: value`` lines and JSON-decoding each value, so the escaping
    tests are not circular. List blocks (``warnings:``) and their ``- `` items are
    skipped.
    """
    if not markdown.startswith("---\n"):
        raise AssertionError("document does not start with YAML frontmatter")
    end = markdown.index("\n---\n", 3)
    block = markdown[4:end]
    values = {}
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            continue
        raw = raw.strip()
        if not raw:
            continue  # list header such as "warnings:"
        values[key.strip()] = json.loads(raw)
    return values


def body_of(markdown):
    """Return the Markdown body with the frontmatter block stripped."""
    end = markdown.index("\n---\n", 3)
    return markdown[end + len("\n---\n") :]


class FakeResponse:
    """Minimal stand-in for ``x2md.HttpResponse``."""

    def __init__(self, status, url, body, headers=None):
        self.status = status
        self.url = url
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.headers = headers or {}

    def json(self):
        return json.loads(self.body.decode("utf-8", "replace"))

    def text(self):
        return self.body.decode("utf-8", "replace")


class FakeHttp:
    """Scripted HTTP layer used in place of ``x2md.HttpClient.request``.

    ``routes`` maps a substring of the request URL to either a fixture filename or
    a ``(status, body)`` tuple; the first matching route wins. Requests matching no
    route return 404 so tests fail loudly instead of silently reaching the network.
    """

    def __init__(self, routes, default_status=404):
        self.routes = list(routes.items())
        self.default_status = default_status
        self.calls = []

    def resolve(self, url):
        # Exact match wins over substring match. Without this, the route for
        # "/2/thread/20" would also swallow "/2/thread/2072439205213421694",
        # because the former is a prefix of the latter.
        candidates = []
        for needle, target in self.routes:
            if needle == url:
                candidates = [(needle, target)]
                break
            if needle in url:
                candidates.append((needle, target))
        for _needle, target in candidates:
            if isinstance(target, tuple):
                status, payload = target
            else:
                status, payload = 200, target
            if isinstance(payload, str) and payload.endswith((".json", ".html")):
                payload = load_fixture_text(payload)
            return status, payload
        return self.default_status, '{"code":404,"message":"no fixture route"}'

    def urls(self):
        return [call["url"] for call in self.calls]


def install_fake_http(routes, default_status=404):
    """Patch ``x2md.HttpClient.request`` with a stub.

    The stub is installed as a *function* (not a bare callable object) so that it
    is bound as a method: it receives the real ``HttpClient`` as ``self`` and can
    therefore drive the client's own debug logging and request accounting, exactly
    like the real implementation would.
    """
    fake = FakeHttp(routes, default_status=default_status)

    def request(self, url, method="GET", headers=None, body=None, provider="-"):
        status, payload = fake.resolve(url)
        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        fake.calls.append(
            {
                "url": url,
                "method": method,
                "provider": provider,
                "status": status,
                "headers": dict(headers or {}),
            }
        )
        self.request_count += 1
        self._log(
            "%s %s %s -> HTTP %s, %d bytes" % (provider, method, url, status, len(encoded))
        )
        return FakeResponse(status, url, encoded)

    x2md.HttpClient.request = request
    return fake


# Captured once, at import, so restoring is reliable regardless of test order.
ORIGINAL_REQUEST = x2md.HttpClient.request


def restore_http():
    """Undo :func:`install_fake_http`."""
    x2md.HttpClient.request = ORIGINAL_REQUEST


def run_cli(args, routes=None, default_status=404):
    """Run ``x2md.main`` with the network layer stubbed out.

    The stub is *always* installed -- even with no routes -- so that no test in
    this suite can ever reach the live network. Returns
    ``(exit_code, stderr_text, fake)``; ``exit_code`` is None when argparse exits
    via SystemExit (e.g. ``--help`` or a bad choice), in which case the code is
    returned instead.
    """
    import contextlib
    import io

    fake = install_fake_http(routes or {}, default_status=default_status)
    stderr = io.StringIO()
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            code = x2md.main(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
    finally:
        restore_http()
    return code, stderr.getvalue(), fake
