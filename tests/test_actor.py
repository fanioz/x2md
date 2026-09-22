"""Tests for the Apify Actor mapping layer (src/actor_lib.py).

Offline: every network touch goes through the FakeHttp layer from _support,
so the suite passes with X2MD_TEST_BLOCK_NETWORK=1. The apify SDK itself is
never imported here; actor_lib is stdlib-only and SDK calls live in main.py.
"""

import unittest

import _support

x2md = _support.x2md
actor_lib = _support.load_actor_lib()

STATUS_SIMPLE = "fxtwitter_v2_status_simple.json"
THREAD5 = "fxtwitter_v2_thread5.json"
VIDEO = "fxtwitter_v2_video.json"

BASE_INPUT = {
    "startUrls": ["https://x.com/jack/status/20"],
    "maxItems": 10,
    "provider": "auto",
    "downloadMedia": {"images": True, "videos": True, "gifs": True, "zip": True},
    "outputFormat": "both",
}

THREAD_URL = "https://x.com/XCreators/status/2072439205213421694"
VIDEO_URL = "https://x.com/imagine/status/2095249317875622255"


def routes_for(status_id, thread_fixture=None, status_fixture=STATUS_SIMPLE):
    """Full-URL routes so substring matching cannot cross wires (see memory)."""
    routes = {
        "https://api.fxtwitter.com/2/status/%s" % status_id: status_fixture,
    }
    routes["https://api.fxtwitter.com/2/thread/%s" % status_id] = (
        thread_fixture or status_fixture
    )
    return routes


class ValidateInputTest(unittest.TestCase):
    def test_valid_minimal_input_defaults_media_off(self):
        cleaned = actor_lib.validate_input({"startUrls": ["https://x.com/jack/status/20"]})
        self.assertEqual(cleaned["maxItems"], 10)
        self.assertEqual(cleaned["provider"], "auto")
        self.assertEqual(cleaned["outputFormat"], "both")
        self.assertFalse(any(cleaned["downloadMedia"].values()))

    def test_bare_id_accepted(self):
        cleaned = actor_lib.validate_input({"startUrls": ["20"]})
        self.assertEqual(cleaned["startUrls"], ["20"])

    def test_request_list_sources_objects_accepted(self):
        cleaned = actor_lib.validate_input({"startUrls": [{"url": "https://x.com/jack/status/20"}]})
        self.assertEqual(cleaned["startUrls"], ["https://x.com/jack/status/20"])

    def test_missing_start_urls_rejected(self):
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({})

    def test_empty_start_urls_rejected(self):
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": []})

    def test_max_items_clamped_to_platform_limit(self):
        cleaned = actor_lib.validate_input(
            {"startUrls": ["https://x.com/jack/status/20"], "maxItems": 500}
        )
        self.assertEqual(cleaned["maxItems"], 50)

    def test_max_items_floor(self):
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "maxItems": 0})

    def test_unknown_provider_rejected(self):
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "provider": "carrier-pigeon"})

    def test_bad_output_format_rejected(self):
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "outputFormat": "sideways"})

    def test_partial_download_media_toggles(self):
        cleaned = actor_lib.validate_input(
            {"startUrls": ["20"], "downloadMedia": {"images": True}}
        )
        self.assertTrue(cleaned["downloadMedia"]["images"])
        self.assertFalse(cleaned["downloadMedia"]["videos"])


class FetchOneTest(unittest.TestCase):
    def test_single_post_first_provider_wins(self):
        fake = _support.install_fake_http(routes_for("20"))
        try:
            item = actor_lib.fetch_one("https://x.com/jack/status/20", BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertEqual(item["id"], "20")
        self.assertEqual(item["kind"], "post")
        self.assertEqual(item["provider"], "fxtwitter")
        self.assertEqual(item["providerErrors"], [])
        self.assertIn("just setting up my twttr", item["markdown"])
        self.assertEqual(len(item["posts"]), 1)
        self.assertEqual(item["posts"][0]["threadPosition"], None)

    def test_total_failure_yields_failed_providers_chain(self):
        fake = _support.install_fake_http(
            {"https://api.fxtwitter.com": (200, '{"code":404,"message":"NOT_FOUND"}')}
        )
        try:
            item = actor_lib.fetch_one("https://x.com/x/status/999", BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertIn("failedProviders", item)
        names = [e["provider"] for e in item["failedProviders"]]
        self.assertIn("fxtwitter", names)
        self.assertIn("vxtwitter", names)
        self.assertIn("syndication", names)

    def test_invalid_url_reported_as_item_error(self):
        item = actor_lib.fetch_one("not a url at all !!!", BASE_INPUT)
        self.assertIn("error", item)
        self.assertIn("url", item)


class ThreadMappingTest(unittest.TestCase):
    def test_thread_flat_and_nested(self):
        _support.install_fake_http(routes_for("2072439205213421694", THREAD5, THREAD5))
        try:
            item = actor_lib.fetch_one(THREAD_URL, BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertEqual(item["kind"], "thread")
        self.assertEqual(len(item["posts"]), 5)
        positions = [p["threadPosition"] for p in item["posts"]]
        self.assertEqual(positions, [1, 2, 3, 4, 5])
        self.assertIn("thread", item)
        self.assertEqual(len(item["thread"]["posts"]), 5)

    def test_flat_only_omits_nested_thread(self):
        _support.install_fake_http(routes_for("2072439205213421694", THREAD5, THREAD5))
        try:
            item = actor_lib.fetch_one(THREAD_URL, dict(BASE_INPUT, outputFormat="flat"))
        finally:
            _support.restore_http()
        self.assertIn("posts", item)
        self.assertNotIn("thread", item)


class MediaKeysTest(unittest.TestCase):
    def test_video_gets_mp4_file_key_with_timestamp(self):
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        try:
            item = actor_lib.fetch_one(VIDEO_URL, BASE_INPUT)
        finally:
            _support.restore_http()
        media = item["posts"][0]["media"]
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["type"], "video")
        key = media[0]["fileKey"]
        self.assertTrue(key.startswith("video/imagine_2095249317875622255_"))
        self.assertTrue(key.endswith(".mp4"))
        self.assertLessEqual(len(key), 256)

    def test_media_disabled_yields_null_file_keys(self):
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        no_media = dict(BASE_INPUT, downloadMedia={})
        try:
            item = actor_lib.fetch_one(VIDEO_URL, actor_lib.validate_input(no_media))
        finally:
            _support.restore_http()
        self.assertIsNone(item["posts"][0]["media"][0]["fileKey"])

    def test_kv_key_helpers(self):
        key = actor_lib.media_file_key("image", "jack", "20", 0, 1758230400000)
        self.assertEqual(key, "image/jack_20_1758230400000_p0.jpg")
        video_key = actor_lib.media_file_key("video", "jack", "20", 0, 1758230400000)
        self.assertTrue(video_key.endswith(".mp4"))


class MediaDownloadPlanTest(unittest.TestCase):
    def test_plan_lists_best_asset_per_toggle(self):
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        try:
            target = x2md.parse_target(VIDEO_URL)
            client = x2md.HttpClient()
            providers = x2md.build_providers("auto", client, {})
            doc, _ = x2md.fetch_document(target, providers, client)
        finally:
            _support.restore_http()
        plan = actor_lib.plan_media_downloads(doc, BASE_INPUT["downloadMedia"], 1758230400000)
        self.assertEqual(len(plan), 1)
        self.assertTrue(plan[0]["download_url"].endswith(".mp4?tag=29"))
        self.assertTrue(plan[0]["key"].endswith(".mp4"))

    def test_plan_empty_when_toggles_off(self):
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        try:
            target = x2md.parse_target(VIDEO_URL)
            client = x2md.HttpClient()
            providers = x2md.build_providers("auto", client, {})
            doc, _ = x2md.fetch_document(target, providers, client)
        finally:
            _support.restore_http()
        self.assertEqual(actor_lib.plan_media_downloads(doc, {}, 0), [])


class RunBatchTest(unittest.TestCase):
    def test_batch_respects_max_items(self):
        _support.install_fake_http(
            {
                **routes_for("20"),
                **routes_for("2072439205213421694", THREAD5, THREAD5),
            }
        )
        try:
            cleaned = actor_lib.validate_input(
                {
                    "startUrls": [
                        "https://x.com/jack/status/20",
                        THREAD_URL,
                    ],
                    "maxItems": 1,
                }
            )
            result = actor_lib.run_batch(cleaned)
        finally:
            _support.restore_http()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], "20")

    def test_zip_key_present_when_requested(self):
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        single_video = dict(
            BASE_INPUT, startUrls=["https://x.com/imagine/status/2095249317875622255"]
        )
        try:
            result = actor_lib.run_batch(actor_lib.validate_input(single_video))
        finally:
            _support.restore_http()
        self.assertTrue(any(k.startswith("zip/run_") for k in result["kv_keys"]))


if __name__ == "__main__":
    unittest.main()
