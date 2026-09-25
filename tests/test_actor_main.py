"""Smoke-test the Actor entry point without the apify SDK or network.

``src/main.py`` imports ``apify`` at module load, and the SDK currently
fails to import in this environment (upstream pydantic/crawlee conflict),
so this test injects a stub ``apify`` module plus stub HTTP fixtures and
verifies the end-to-end wiring: validate input -> fetch_one per URL ->
push_data per item -> set_value per media file -> ZIP bundle.
"""

import asyncio
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _support  # noqa: E402

x2md = _support.x2md

# The network guard in _support replaces socket.socket with a raiser to prove
# the suite is offline. asyncio's event loop needs one socketpair at loop
# creation, so asyncio.run() cannot work under the guard. Skip this module
# when the guard is active; the test still runs in the normal suite.
if _support.NETWORK_GUARD_ACTIVE:
    raise unittest.SkipTest("asyncio event loop needs a socketpair; offline suite covers actor_lib")


class FakeActor:
    """Minimal stand-in for the apify Actor used by src/main.py."""

    Instance = None
    pushed = None
    stored = None
    proxy_url = None

    def __init__(self):
        """Initialize empty input, output, storage, and proxy state."""
        FakeActor.Instance = self
        self.input = {}
        self.pushed = []
        self.stored = {}
        self.proxy_url = None

    async def __aenter__(self):
        """Enter the fake Actor context."""
        return self

    async def __aexit__(self, *args):
        """Leave the fake Actor context without suppressing errors."""
        return False

    async def get_input(self):
        """Return a copy of the configured Actor input."""
        return dict(self.input)

    async def push_data(self, data, event_name=None):
        """Record a dataset item and its optional charge event."""
        self.pushed.append((data, event_name))

    async def set_value(self, key, value, content_type=None):
        """Record bytes and content type under a storage key."""
        self.stored[key] = (bytes(value), content_type)

    async def get_value(self, key):
        """Return stored bytes for a key, if present."""
        record = self.stored.get(key)
        return record[0] if record else None

    async def create_proxy_configuration(self, actor_proxy_input=None):
        """Simulate an Actor run without a configured proxy."""
        return None

    @property
    def log(self):
        """Provide the logger used by the Actor entry point."""
        import logging

        return logging.getLogger("actor-smoke")


def load_main_with_stub():
    """Import the entry point against a fresh fake Apify module."""
    import types

    stub = types.ModuleType("apify")
    stub.Actor = FakeActor()
    sys.modules["apify"] = stub
    for name in [m for m in list(sys.modules) if m in ("main", "actor_lib")]:
        del sys.modules[name]
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    import importlib

    return importlib.import_module("main")


class MainSmokeTest(unittest.TestCase):
    def test_full_run_offline(self):
        """The entry point publishes items, media, and a ZIP offline."""
        _support.install_fake_http(
            {
                "https://api.fxtwitter.com/2/thread/20": "fxtwitter_v2_status_simple.json",
                "https://api.fxtwitter.com/2/status/20": "fxtwitter_v2_status_simple.json",
                "https://api.fxtwitter.com/2/thread/2095249317875622255": "fxtwitter_v2_video.json",
                "https://api.fxtwitter.com/2/status/2095249317875622255": "fxtwitter_v2_video.json",
                "https://api.fxtwitter.com/2/thread/2088006016721940988": "fxtwitter_v2_photos.json",
                "https://api.fxtwitter.com/2/status/2088006016721940988": "fxtwitter_v2_photos.json",
            }
        )
        main = load_main_with_stub()
        from apify import Actor as actor

        actor.input = {
            "startUrls": [
                "https://x.com/jack/status/20",
                "https://x.com/imagine/status/2095249317875622255",
                "https://x.com/XCreators/status/2088006016721940988",
            ],
            "maxItems": 10,
            "provider": "auto",
            "downloadMedia": {"images": True, "videos": True, "gifs": True, "zip": True},
            "outputFormat": "both",
        }
        orig_download = main._download_bytes
        main._download_bytes = lambda url, timeout=30: (b"FAKE-" + url.encode()[:20], "image/png")
        try:
            asyncio.run(main.main())
        finally:
            main._download_bytes = orig_download
            _support.restore_http()

        try:
            self.assertEqual(len(actor.pushed), 3)
            items = [data for data, _event in actor.pushed]
            self.assertEqual(items[0]["id"], "20")
            self.assertEqual(items[1]["kind"], "post")
            # dataset-item charge event passed through
            self.assertEqual(actor.pushed[0][1], "dataset-item")
            # video + image bytes uploaded + ZIP bundle created
            video_keys = [k for k in actor.stored if k.startswith("video_")]
            self.assertEqual(len(video_keys), 1)
            image_keys = [k for k in actor.stored if k.startswith("image_")]
            self.assertEqual(len(image_keys), 1)
            # The response Content-Type is stored verbatim, proving passthrough.
            self.assertEqual(actor.stored[image_keys[0]][1], "image/png")
            zip_keys = [k for k in actor.stored if k.startswith("zip_")]
            self.assertEqual(len(zip_keys), 1)
            archive = zipfile.ZipFile(io.BytesIO(actor.stored[zip_keys[0]][0]))
            self.assertEqual(len(archive.namelist()), 2)
        finally:
            sys.modules.pop("apify", None)
            sys.modules.pop("main", None)


if __name__ == "__main__":
    unittest.main()
