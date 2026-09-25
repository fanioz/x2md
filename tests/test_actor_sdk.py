"""End-to-end smoke test of the Actor against the real Apify SDK.

This module only runs when the ``apify`` package is importable in the current
interpreter. It spawns ``python3 -m src`` in a subprocess with a temporary
``sitecustomize.py`` that stubs the network layer, so each run gets a fresh
Actor process and fresh local storage.

The test is skipped by default in the offline suite (``X2MD_TEST_BLOCK_NETWORK=1``)
because the Apify SDK needs a real socketpair to start its event loop.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

SITECUSTOMIZE = '''
# Auto-installed by tests/test_actor_sdk.py to stub network inside Actor runs.
import json, os, sys
routes_json = os.environ.get("X2MD_ACTOR_SDK_ROUTES")
if routes_json:
    sys.path.insert(0, {tests_dir!r})
    import _support
    _support.install_fake_http(json.loads(routes_json))
'''


def _sdk_importable():
    """Return whether the real Apify SDK can load in this interpreter."""
    try:
        __import__("apify")
    except Exception:
        return False
    return True


@unittest.skipIf(os.environ.get("X2MD_TEST_BLOCK_NETWORK") == "1", "SDK needs sockets")
@unittest.skipUnless(_sdk_importable(), "apify SDK not installed")
class ActorSdkRunTest(unittest.TestCase):
    def _run_actor(self, input_data, routes):
        """Run ``python3 -m src`` with stubbed HTTP and return dataset items."""
        storage = tempfile.mkdtemp(prefix="x2md-sdk-")
        self.addCleanup(shutil.rmtree, storage, ignore_errors=True)

        shim_dir = tempfile.mkdtemp(prefix="x2md-shim-")
        self.addCleanup(shutil.rmtree, shim_dir, ignore_errors=True)
        shim = pathlib.Path(shim_dir) / "sitecustomize.py"
        shim.write_text(SITECUSTOMIZE.format(tests_dir=str(HERE)))

        kv = pathlib.Path(storage) / "key_value_stores" / "default"
        kv.mkdir(parents=True)
        (kv / "INPUT.json").write_text(json.dumps(input_data))

        env = os.environ.copy()
        env["APIFY_LOCAL_STORAGE_DIR"] = storage
        env["CRAWLEE_STORAGE_DIR"] = storage
        env["X2MD_ACTOR_SDK_ROUTES"] = json.dumps(routes)
        env["PYTHONPATH"] = str(REPO) + os.pathsep + str(shim_dir)

        proc = subprocess.run(
            [sys.executable, "-m", "src"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            self.fail(
                "Actor run failed (exit %d)\nstdout:\n%s\nstderr:\n%s"
                % (proc.returncode, proc.stdout, proc.stderr)
            )

        ds_dir = pathlib.Path(storage) / "datasets" / "default"
        items = []
        for path in sorted(ds_dir.glob("*.json")):
            # __metadata__.json is the dataset metadata, not a data item.
            if path.name.startswith("__"):
                continue
            items.append(json.loads(path.read_text(encoding="utf-8")))
        return items

    def test_single_post_run_offline(self):
        """Real SDK + stubbed HTTP produces a dataset item."""
        routes = {
            "https://api.fxtwitter.com/2/status/20": "fxtwitter_v2_status_simple.json",
            "https://api.fxtwitter.com/2/thread/20": "fxtwitter_v2_status_simple.json",
        }
        items = self._run_actor(
            {
                "startUrls": ["https://x.com/jack/status/20"],
                "maxItems": 5,
                "provider": "auto",
                "downloadMedia": {"images": False, "videos": False, "gifs": False, "zip": False},
                "outputFormat": "both",
            },
            routes,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "20")
        self.assertEqual(items[0]["kind"], "post")
        self.assertEqual(items[0]["provider"], "fxtwitter")
        self.assertIn("markdown", items[0])

    def test_thread_run_offline(self):
        """Real SDK + stubbed HTTP handles a thread and emits nested output."""
        routes = {
            "https://api.fxtwitter.com/2/status/2072439205213421694": "fxtwitter_v2_thread5.json",
            "https://api.fxtwitter.com/2/thread/2072439205213421694": "fxtwitter_v2_thread5.json",
        }
        items = self._run_actor(
            {
                "startUrls": ["https://x.com/XCreators/status/2072439205213421694"],
                "maxItems": 5,
                "provider": "auto",
                "downloadMedia": {"images": False, "videos": False, "gifs": False, "zip": False},
                "outputFormat": "both",
            },
            routes,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "thread")
        self.assertEqual(len(items[0]["posts"]), 5)
        self.assertIn("thread", items[0])


if __name__ == "__main__":
    unittest.main()
