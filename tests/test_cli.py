"""End-to-end CLI behaviour, exercised offline through a stubbed HTTP layer."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md

SIMPLE = "fxtwitter_v2_status_simple.json"
THREAD = "fxtwitter_v2_thread5.json"
ARTICLE = "fxtwitter_v2_article.json"

JACK = "20"
THREAD_ID = "2072439205213421694"
ARTICLE_ID = "2097390372670575039"


def fx_routes(post_id, fixture):
    """Exact-URL routes for the two fxtwitter v2 endpoints of a single post.

    Exact URLs (rather than substrings) matter: `/2/thread/20` is a substring of
    both `/2/thread/2072...` and `/2/thread/20`, so substring routing silently
    serves the wrong fixture.
    """
    return {
        "https://api.fxtwitter.com/2/thread/%s" % post_id: fixture,
        "https://api.fxtwitter.com/2/status/%s" % post_id: fixture,
    }


class TestHelpIsUsable(unittest.TestCase):
    """Acceptance: `--help` must run and exit 0, showing all flags."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(_support.X2MD_PY), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        for flag in (
            "--output",
            "--outdir",
            "--json",
            "--provider",
            "--debug",
            "--graphql-query-id",
            "--auth-file",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, result.stdout)

    def test_help_lists_every_provider(self):
        result = subprocess.run(
            [sys.executable, str(_support.X2MD_PY), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        for name in ("auto", "fxtwitter", "vxtwitter", "syndication", "graphql"):
            with self.subTest(provider=name):
                self.assertIn(name, result.stdout)

    def test_version_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(_support.X2MD_PY), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("x2md", result.stdout)

    def test_no_arguments_is_a_usage_error(self):
        result = subprocess.run(
            [sys.executable, str(_support.X2MD_PY)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 2)


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_single_post_writes_a_markdown_file(self):
        out = self.dir / "post.md"
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "-o", str(out)], fx_routes(JACK, SIMPLE)
        )
        self.assertEqual(code, 0, err)
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("# Post by jack (@jack)", text)
        self.assertIn("just setting up my twttr", text)

    def test_outdir_creates_handle_and_id_filename(self):
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "--outdir", str(self.dir)],
            fx_routes(JACK, SIMPLE),
        )
        self.assertEqual(code, 0, err)
        self.assertTrue((self.dir / "jack_20.md").is_file())

    def test_stdout_destination(self):
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "-o", "-"], fx_routes(JACK, SIMPLE)
        )
        self.assertEqual(code, 0, err)

    def test_thread_document_is_single_numbered_document(self):
        out = self.dir / "thread.md"
        code, err, _ = _support.run_cli(
            ["https://x.com/XCreators/status/%s" % THREAD_ID, "-o", str(out)],
            fx_routes(THREAD_ID, THREAD),
        )
        self.assertEqual(code, 0, err)
        text = out.read_text(encoding="utf-8")
        self.assertIn("kind: \"thread\"", text)
        self.assertIn("## 1/5", text)
        self.assertIn("## 5/5", text)
        self.assertEqual(text.count("## "), 5)

    def test_json_output_is_valid_and_normalized(self):
        out = self.dir / "post.json"
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "--json", "-o", str(out)],
            fx_routes(JACK, SIMPLE),
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "post")
        self.assertEqual(payload["status_id"], "20")
        self.assertEqual(payload["author"]["handle"], "jack")
        self.assertIn("likes", payload["posts"][0]["stats"])

    def test_multiple_urls_each_get_a_file(self):
        routes = dict(fx_routes(JACK, SIMPLE))
        routes.update(fx_routes(THREAD_ID, THREAD))
        code, err, _ = _support.run_cli(
            ["20", THREAD_ID, "--outdir", str(self.dir)], routes
        )
        self.assertEqual(code, 0, err)
        self.assertTrue((self.dir / "jack_20.md").is_file())
        self.assertTrue((self.dir / "XCreators_2072439205213421694.md").is_file())

    def test_output_flag_with_multiple_urls_is_rejected(self):
        code, err, _ = _support.run_cli(
            ["20", THREAD_ID, "-o", str(self.dir / "x.md")], fx_routes(JACK, SIMPLE)
        )
        self.assertEqual(code, 2)
        self.assertIn("--outdir", err)


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_invalid_url_exits_2(self):
        code, err, _ = _support.run_cli(["https://example.com/jack/status/20"])
        self.assertEqual(code, 2)
        self.assertIn("unsupported host", err)

    def test_garbage_argument_exits_2(self):
        code, err, _ = _support.run_cli(["not a url at all"])
        self.assertEqual(code, 2)

    def test_unknown_provider_exits_2(self):
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "--provider", "nope"]
        )
        self.assertEqual(code, 2)

    def test_all_providers_failing_exits_1_and_names_each_provider(self):
        code, err, _ = _support.run_cli(
            ["https://x.com/jack/status/20", "-o", str(self.dir / "x.md")],
            default_status=500,
        )
        self.assertEqual(code, 1)
        for name in ("fxtwitter", "vxtwitter", "syndication"):
            with self.subTest(provider=name):
                self.assertIn(name, err)

    def test_cloudflare_interstitial_is_reported_not_crashed(self):
        body = _support.load_fixture_text("vxtwitter_cloudflare_challenge.html")
        code, err, _ = _support.run_cli(
            [
                "https://x.com/jack/status/20",
                "--provider",
                "vxtwitter",
                "-o",
                str(self.dir / "x.md"),
            ],
            {"api.vxtwitter.com": body},
        )
        self.assertEqual(code, 1)
        self.assertIn("HTML", err)

    def test_graphql_without_query_id_reports_the_reason(self):
        code, err, _ = _support.run_cli(
            [
                "https://x.com/jack/status/20",
                "--provider",
                "graphql",
                "-o",
                str(self.dir / "x.md"),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("query id", err)


class TestDebugOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_debug_prints_endpoint_and_http_status(self):
        code, err, _ = _support.run_cli(
            [
                "https://x.com/jack/status/20",
                "--debug",
                "-o",
                str(self.dir / "x.md"),
            ],
            fx_routes(JACK, SIMPLE),
        )
        self.assertEqual(code, 0, err)
        self.assertIn("[debug]", err)
        self.assertIn("HTTP 200", err)
        self.assertIn("https://api.fxtwitter.com/", err)

    def test_debug_reports_a_failed_provider_attempt(self):
        code, err, _ = _support.run_cli(
            [
                "https://x.com/jack/status/20",
                "--debug",
                "-o",
                str(self.dir / "x.md"),
            ],
            {
                "https://api.fxtwitter.com/2/thread/20": (503, "down"),
                "https://api.fxtwitter.com/2/status/20": (503, "down"),
                "https://api.vxtwitter.com/jack/status/20": "vxtwitter_status_simple.json",
            },
        )
        self.assertEqual(code, 0, err)
        self.assertIn("HTTP 503", err)
        self.assertIn("vxtwitter", err)


class TestProviderSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_forced_provider_is_recorded_in_frontmatter(self):
        out = self.dir / "p.md"
        code, err, _ = _support.run_cli(
            [
                "https://x.com/jack/status/20",
                "--provider",
                "fxtwitter",
                "-o",
                str(out),
            ],
            fx_routes(JACK, SIMPLE),
        )
        self.assertEqual(code, 0, err)
        self.assertIn('provider: "fxtwitter"', out.read_text(encoding="utf-8"))

    def test_auto_only_asks_the_winning_provider(self):
        out = self.dir / "a.md"
        code, err, fake = _support.run_cli(
            ["https://x.com/jack/status/20", "-o", str(out)], fx_routes(JACK, SIMPLE)
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(fake.calls)
        self.assertTrue(all("fxtwitter" in url for url in fake.urls()))

    def test_article_via_cli(self):
        out = self.dir / "art.md"
        code, err, _ = _support.run_cli(
            ["https://x.com/XBusiness/status/2097390372670575039", "-o", str(out)],
            fx_routes(ARTICLE_ID, ARTICLE),
        )
        self.assertEqual(code, 0, err)
        text = out.read_text(encoding="utf-8")
        self.assertIn('kind: "article"', text)
        self.assertIn("# If you blinked this summer", text)


class TestNoNetworkDependency(unittest.TestCase):
    """Without any network access the tool must still fail cleanly, not hang."""

    def test_unsupported_host_never_reaches_the_network(self):
        code, err, fake = _support.run_cli(["https://evil.example/x/status/20"])
        self.assertEqual(code, 2)
        self.assertIn("unsupported host", err)
        # The stub is always installed; asserting it saw no calls proves the bad
        # argument was rejected before any retrieval was attempted.
        self.assertEqual(fake.calls, [])

    def test_module_has_no_third_party_imports(self):
        source = _support.X2MD_PY.read_text(encoding="utf-8")
        for banned in ("import requests", "import httpx", "import yaml", "from bs4"):
            with self.subTest(module=banned):
                self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
