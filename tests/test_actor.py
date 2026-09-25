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
THREAD_INCOMPLETE = "fxtwitter_v2_thread_incomplete.json"
THREAD100 = "fxtwitter_v2_thread100.json"
VIDEO = "fxtwitter_v2_video.json"
POLL = "fxtwitter_v2_poll.json"
QUOTE = "fxtwitter_v2_quote.json"
ARTICLE = "fxtwitter_v2_article.json"
ARTICLE_MEDIA = "fxtwitter_v2_article_media.json"

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
        """Minimal input gets defaults without media downloads."""
        cleaned = actor_lib.validate_input({"startUrls": ["https://x.com/jack/status/20"]})
        self.assertEqual(cleaned["maxItems"], 10)
        self.assertEqual(cleaned["provider"], "auto")
        self.assertEqual(cleaned["outputFormat"], "both")
        self.assertFalse(any(cleaned["downloadMedia"].values()))

    def test_bare_id_accepted(self):
        """A bare post ID is accepted as a start URL."""
        cleaned = actor_lib.validate_input({"startUrls": ["20"]})
        self.assertEqual(cleaned["startUrls"], ["20"])

    def test_request_list_sources_objects_accepted(self):
        """Request-list objects are reduced to their URL strings."""
        cleaned = actor_lib.validate_input({"startUrls": [{"url": "https://x.com/jack/status/20"}]})
        self.assertEqual(cleaned["startUrls"], ["https://x.com/jack/status/20"])

    def test_missing_start_urls_rejected(self):
        """Input without startUrls is rejected."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({})

    def test_empty_start_urls_rejected(self):
        """An empty startUrls list is rejected."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": []})

    def test_max_items_above_cap_is_rejected(self):
        """The platform item cap rejects larger maxItems values."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input(
                {"startUrls": ["https://x.com/jack/status/20"], "maxItems": 500}
            )

    def test_max_items_at_cap_is_accepted(self):
        """The maximum permitted maxItems value is accepted."""
        cleaned = actor_lib.validate_input(
            {"startUrls": ["https://x.com/jack/status/20"], "maxItems": 50}
        )
        self.assertEqual(cleaned["maxItems"], 50)

    def test_max_items_floor(self):
        """Zero maxItems is rejected."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "maxItems": 0})

    def test_unknown_provider_rejected(self):
        """Unknown provider names are rejected."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "provider": "carrier-pigeon"})

    def test_bad_output_format_rejected(self):
        """Unknown output formats are rejected."""
        with self.assertRaises(actor_lib.ActorInputError):
            actor_lib.validate_input({"startUrls": ["20"], "outputFormat": "sideways"})

    def test_partial_download_media_toggles(self):
        """Unspecified media toggles stay disabled."""
        cleaned = actor_lib.validate_input(
            {"startUrls": ["20"], "downloadMedia": {"images": True}}
        )
        self.assertTrue(cleaned["downloadMedia"]["images"])
        self.assertFalse(cleaned["downloadMedia"]["videos"])


class FetchOneTest(unittest.TestCase):
    def test_single_post_first_provider_wins(self):
        """A successful first provider supplies the single-post item."""
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
        """Total failure preserves each attempted provider error."""
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
        """Malformed URLs produce an item-level error."""
        item = actor_lib.fetch_one("not a url at all !!!", BASE_INPUT)
        self.assertIn("error", item)
        self.assertIn("url", item)

    def test_unexpected_exception_isolated_per_url(self):
        """A bug inside fetch_document must come back as an error item, not abort."""
        original = x2md.fetch_document

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        x2md.fetch_document = boom
        try:
            item = actor_lib.fetch_one("https://x.com/jack/status/20", BASE_INPUT)
        finally:
            x2md.fetch_document = original
        self.assertEqual(item["url"], "https://x.com/jack/status/20")
        self.assertIn("boom", item["error"])


class ThreadMappingTest(unittest.TestCase):
    def test_thread_flat_and_nested(self):
        """Thread output includes ordered flat and nested posts."""
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
        """Flat output omits the nested thread object."""
        _support.install_fake_http(routes_for("2072439205213421694", THREAD5, THREAD5))
        try:
            item = actor_lib.fetch_one(THREAD_URL, dict(BASE_INPUT, outputFormat="flat"))
        finally:
            _support.restore_http()
        self.assertIn("posts", item)
        self.assertNotIn("thread", item)

    def test_nested_output_keeps_posts_for_non_thread(self):
        """Nested-only output must not drop the structured payload of a post."""
        _support.install_fake_http(routes_for("20"))
        try:
            item = actor_lib.fetch_one(
                "https://x.com/jack/status/20", dict(BASE_INPUT, outputFormat="nested")
            )
        finally:
            _support.restore_http()
        self.assertEqual(item["kind"], "post")
        self.assertTrue(item["posts"])
        self.assertNotIn("thread", item)


class MediaKeysTest(unittest.TestCase):
    def test_video_gets_mp4_file_key_with_timestamp(self):
        """Video downloads receive bounded timestamped MP4 keys."""
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        try:
            item = actor_lib.fetch_one(VIDEO_URL, BASE_INPUT)
        finally:
            _support.restore_http()
        media = item["posts"][0]["media"]
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["type"], "video")
        key = media[0]["fileKey"]
        self.assertTrue(key.startswith("video_imagine_2095249317875622255_"))
        self.assertTrue(key.endswith(".mp4"))
        self.assertLessEqual(len(key), 256)

    def test_media_disabled_yields_null_file_keys(self):
        """Disabled media downloads leave file keys unset."""
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        no_media = dict(BASE_INPUT, downloadMedia={})
        try:
            item = actor_lib.fetch_one(VIDEO_URL, actor_lib.validate_input(no_media))
        finally:
            _support.restore_http()
        self.assertIsNone(item["posts"][0]["media"][0]["fileKey"])

    def test_kv_key_helpers(self):
        """Media key helpers choose the expected prefixes and extensions."""
        key = actor_lib.media_file_key("image", "jack", "20", 0, 1758230400000)
        self.assertEqual(key, "image_jack_20_1758230400000_p0.jpg")
        video_key = actor_lib.media_file_key("video", "jack", "20", 0, 1758230400000)
        self.assertTrue(video_key.endswith(".mp4"))

    def test_gif_assets_keep_their_selected_extension(self):
        """Static GIFs use GIF keys; re-encoded GIFs retain MP4 keys."""
        static_gif = x2md.Media(
            kind="gif", url="https://pbs.twimg.com/media/static.gif?name=orig"
        )
        video_gif = x2md.Media(
            kind="gif",
            url="https://pbs.twimg.com/media/animated.gif?name=orig",
            video_url="https://video.twimg.com/animated.mp4",
        )
        self.assertEqual(actor_lib.best_media_asset(static_gif)[1], "gif")
        self.assertEqual(actor_lib.best_media_asset(video_gif)[1], "mp4")
        ref = actor_lib.media_to_ref(
            static_gif,
            "jack",
            "20",
            0,
            {"gifs": True},
            1758230400000,
        )
        self.assertTrue(ref["fileKey"].endswith(".gif"))

    def test_iter_file_refs_thread_fallback_without_duplicates(self):
        """Nested-only threads expose refs via "thread"; "both" output yields once."""
        nested_only = {"thread": {"posts": [{"media": [{"fileKey": "image_jack_20_1_p0.jpg"}]}]}}
        refs = list(actor_lib.iter_file_refs(nested_only))
        self.assertEqual([ref["fileKey"] for ref in refs], ["image_jack_20_1_p0.jpg"])
        post = {"media": [{"fileKey": "image_jack_20_1_p0.jpg"}]}
        both = {"posts": [post], "thread": {"posts": [post]}}
        self.assertEqual(len(list(actor_lib.iter_file_refs(both))), 1)


class MediaDownloadPlanTest(unittest.TestCase):
    def test_plan_lists_best_asset_per_toggle(self):
        """Download plans select the best enabled media asset."""
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
        """No downloads are planned when all toggles are off."""
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
        """Batch processing stops at the configured item limit."""
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
        """A requested media bundle receives a ZIP storage key."""
        _support.install_fake_http(routes_for("2095249317875622255", VIDEO, VIDEO))
        single_video = dict(
            BASE_INPUT, startUrls=["https://x.com/imagine/status/2095249317875622255"]
        )
        try:
            result = actor_lib.run_batch(actor_lib.validate_input(single_video))
        finally:
            _support.restore_http()
        self.assertTrue(any(k.startswith("zip_run_") for k in result["kv_keys"]))


class ThreadCompletenessTest(unittest.TestCase):
    def test_incomplete_self_reply_warns_thread_incomplete(self):
        """A missing self-thread sibling marks the result incomplete."""
        url = "https://x.com/threadsmith/status/1900000000000000041"
        _support.install_fake_http(routes_for("1900000000000000041", THREAD_INCOMPLETE, THREAD_INCOMPLETE))
        try:
            item = actor_lib.fetch_one(url, BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertEqual(item["kind"], "thread")
        self.assertIs(item["threadComplete"], False)
        self.assertIn(actor_lib.WARNING_THREAD_INCOMPLETE, item["warnings"])
        # The first post in the item is also marked incomplete.
        self.assertIs(item["posts"][0]["threadComplete"], False)

    def test_complete_thread_does_not_warn(self):
        """A complete thread has no incompleteness warning."""
        _support.install_fake_http(routes_for("2072439205213421694", THREAD5, THREAD5))
        try:
            item = actor_lib.fetch_one(THREAD_URL, BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertEqual(item["kind"], "thread")
        self.assertIs(item["threadComplete"], True)
        self.assertNotIn(actor_lib.WARNING_THREAD_INCOMPLETE, item["warnings"])

    def test_max_items_caps_url_count(self):
        """The 50-item cap limits how many startUrls are processed."""
        url = "https://x.com/jack/status/20"
        _support.install_fake_http(routes_for("20"))
        try:
            cleaned = actor_lib.validate_input(
                {"startUrls": [url] * 60, "maxItems": 50}
            )
            result = actor_lib.run_batch(cleaned)
        finally:
            _support.restore_http()
        self.assertEqual(len(result["items"]), actor_lib.MAX_ITEMS_HARD_CAP)

    def test_hundred_post_thread_fits_in_memory(self):
        """A 100-post thread maps without exhausting memory.

        This test is informational: it verifies the fixture runs to completion
        under the network guard, which is the real regression we care about.
        Memory is logged in tracemalloc but not asserted because it varies by
        interpreter and CI runner load.
        """
        import tracemalloc

        url = "https://x.com/threadsmith/status/1900000000000000000"
        _support.install_fake_http(
            routes_for("1900000000000000000", THREAD100, THREAD100)
        )
        try:
            tracemalloc.start()
            item = actor_lib.fetch_one(url, BASE_INPUT)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            # Guarded: a failure before start() must not raise here either,
            # and a fetch_one failure must not leak tracing into the suite.
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            _support.restore_http()
        self.assertEqual(item["kind"], "thread")
        self.assertEqual(len(item["posts"]), 100)
        self.assertIs(item["threadComplete"], True)
        # Informational; printed on failure to help manual triage.
        self.assertLess(peak, 500 * 1024 * 1024, "peak memory unexpectedly high: %.1f MB" % (peak / 1024 / 1024))


class PollQuoteArticleTest(unittest.TestCase):
    def _fetch_doc(self, status_id, fixture):
        """Fetch a document with FakeHttp active for both Actor and CLI paths."""
        _support.install_fake_http(routes_for(status_id, fixture, fixture))
        try:
            url = "https://x.com/example/status/%s" % status_id
            item = actor_lib.fetch_one(url, BASE_INPUT)
            target = x2md.parse_target(url)
            client = x2md.HttpClient()
            providers = x2md.build_providers("auto", client, {})
            doc, _ = x2md.fetch_document(target, providers, client)
            return item, doc
        finally:
            _support.restore_http()

    def test_poll_fields_match_cli(self):
        """Actor poll fields match the CLI JSON serializer."""
        item, doc = self._fetch_doc("1780000000000000001", POLL)
        post = item["posts"][0]
        self.assertIsNotNone(post["poll"])
        self.assertIn("choices", post["poll"])
        self.assertIn("total_votes", post["poll"])
        cli_poll = x2md.document_to_json(doc)["posts"][0]["poll"]
        self.assertEqual(post["poll"], cli_poll)

    def test_quote_fields_match_cli(self):
        """Actor quote fields match the CLI JSON serializer."""
        item, doc = self._fetch_doc("2099922471272976442", QUOTE)
        post = item["posts"][0]
        self.assertIsNotNone(post["quote"])
        self.assertIn("text", post["quote"])
        self.assertIn("author", post["quote"])
        cli_quote = x2md.document_to_json(doc)["posts"][0]["quote"]
        self.assertEqual(post["quote"], cli_quote)

    def test_article_fields_match_cli(self):
        """Actor article fields match the CLI JSON serializer."""
        item, doc = self._fetch_doc("2097390372670575039", ARTICLE)
        post = item["posts"][0]
        self.assertIsNotNone(post["article"])
        for key in ("id", "title", "preview_text", "created_at", "modified_at", "block_count"):
            self.assertIn(key, post["article"])
        cli_article = x2md.document_to_json(doc)["posts"][0]["article"]
        self.assertEqual(post["article"], cli_article)

    def test_article_with_media_keeps_cover_media_shape(self):
        """Article cover media survives Actor mapping."""
        url = "https://x.com/example/status/2085835082166653393"
        _support.install_fake_http(routes_for("2085835082166653393", ARTICLE_MEDIA, ARTICLE_MEDIA))
        try:
            item = actor_lib.fetch_one(url, BASE_INPUT)
        finally:
            _support.restore_http()
        self.assertEqual(item["kind"], "article")
        self.assertIsNotNone(item["posts"][0]["article"])


if __name__ == "__main__":
    unittest.main()
