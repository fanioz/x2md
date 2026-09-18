"""Provider normalization, error reporting and the syndication token."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


class TestSyndicationToken(unittest.TestCase):
    def test_token_is_non_empty_and_base36(self):
        token = x2md.syndication_token("20")
        self.assertTrue(token)
        self.assertRegex(token, r"^[0-9a-z]+$")

    def test_token_is_deterministic(self):
        self.assertEqual(
            x2md.syndication_token("2072439205213421694"),
            x2md.syndication_token("2072439205213421694"),
        )

    def test_token_known_value(self):
        # Pins the exact conversion so a change to the emulation is caught.
        self.assertEqual(
            x2md.syndication_token("20"),
            "6dq1a2xwd91cz35wmb5wn4rku9q2hi3ku14cayvi",
        )

    def test_different_ids_give_different_tokens(self):
        self.assertNotEqual(
            x2md.syndication_token("20"), x2md.syndication_token("21")
        )

    def test_non_numeric_id_falls_back_to_a_constant(self):
        self.assertEqual(x2md.syndication_token("not-a-number"), "x2md")

    def test_observed_tokens_are_accepted_by_the_live_endpoint(self):
        # Documented observation: the endpoint does not validate the token, so any
        # non-empty value works. Asserted here so the assumption is explicit.
        self.assertNotEqual(x2md.syndication_token("20"), "")


class TestJsonGuarding(unittest.TestCase):
    """A bot-protection/interstitial page must produce a clear error, not a crash."""

    def test_cloudflare_challenge_is_reported_clearly(self):
        body = _support.load_fixture_text("vxtwitter_cloudflare_challenge.html")
        response = _support.FakeResponse(200, "https://api.vxtwitter.com/i/status/20", body)
        with self.assertRaises(x2md.ProviderError) as ctx:
            x2md._require_json(response, "vxtwitter")
        message = str(ctx.exception)
        self.assertIn("expected JSON but received HTML", message)
        self.assertIn("bot-protection", message)
        self.assertEqual(ctx.exception.status, 200)

    def test_invalid_json_is_reported(self):
        response = _support.FakeResponse(200, "https://example.com", "not json at all")
        with self.assertRaises(x2md.ProviderError) as ctx:
            x2md._require_json(response, "p")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_valid_json_passes_through(self):
        response = _support.FakeResponse(200, "https://example.com", '{"a": 1}')
        self.assertEqual(x2md._require_json(response, "p"), {"a": 1})

    def test_cloudflare_page_cannot_be_parsed_as_a_tweet(self):
        body = _support.load_fixture_text("vxtwitter_cloudflare_challenge.html")
        _support.install_fake_http({"api.vxtwitter.com": body})
        try:
            provider = x2md.VxTwitterProvider(x2md.HttpClient())
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            self.assertIn("HTML", str(ctx.exception))
        finally:
            _support.restore_http()


class TestVxTwitterNormalization(unittest.TestCase):
    def setUp(self):
        self.payload = _support.load_fixture("vxtwitter_status_video.json")
        self.doc = x2md._document_from_vxtwitter_payload(
            self.payload,
            x2md.parse_target("https://x.com/imagine/status/2095249317875622255"),
            "vxtwitter",
        )

    def test_author_and_id(self):
        self.assertEqual(self.doc.primary.post_id, "2095249317875622255")
        self.assertEqual(self.doc.primary.author.handle, "imagine")
        self.assertEqual(self.doc.primary.author.name, "Grok Imagine")

    def test_video_media_uses_thumbnail_as_link_and_remembers_the_file(self):
        media = self.doc.primary.media
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0].kind, "video")
        self.assertIn("pbs.twimg.com", media[0].url)
        self.assertIn("video.twimg.com", media[0].video_url)
        self.assertAlmostEqual(media[0].duration, 39.2, places=1)

    def test_text_line_breaks_are_preserved(self):
        self.assertIn("\n", self.doc.primary.text)
        self.assertIn("You can now use up to 14 references", self.doc.primary.text)

    def test_text_is_html_escaped(self):
        payload = dict(self.payload)
        payload["text"] = "<script>bad()</script>"
        doc = x2md._document_from_vxtwitter_payload(
            payload, x2md.parse_target("20"), "vxtwitter"
        )
        self.assertNotIn("<script>", doc.primary.text)
        self.assertIn("&lt;script&gt;", doc.primary.text)


class TestSyndicationNormalization(unittest.TestCase):
    def setUp(self):
        self.payload = _support.load_fixture("syndication_quote.json")
        self.doc = x2md._document_from_syndication_payload(
            self.payload,
            x2md.parse_target("https://x.com/XCreators/status/2099922471272976442"),
            "syndication",
        )

    def test_author_and_id(self):
        self.assertEqual(self.doc.primary.post_id, "2099922471272976442")
        self.assertEqual(self.doc.primary.author.handle, "XCreators")
        self.assertEqual(self.doc.primary.author.author_id, "3282859598")

    def test_quoted_post_is_normalized_with_its_own_author_and_media(self):
        quote = self.doc.primary.quote
        self.assertIsNotNone(quote)
        self.assertEqual(quote.author.handle, "grok")
        self.assertEqual(quote.post_id, "2099876430561632548")
        self.assertTrue(quote.media)
        self.assertEqual(quote.media[0].kind, "video")

    def test_main_post_has_no_photo_media(self):
        self.assertEqual(self.doc.primary.media, [])

    def test_empty_body_is_rejected(self):
        _support.install_fake_http({"cdn.syndication.twimg.com": (200, "")})
        try:
            provider = x2md.SyndicationProvider(x2md.HttpClient())
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            self.assertIn("empty response body", str(ctx.exception))
        finally:
            _support.restore_http()

    def test_missing_id_str_is_rejected(self):
        _support.install_fake_http({"cdn.syndication.twimg.com": (200, '{"text":"x"}')})
        try:
            provider = x2md.SyndicationProvider(x2md.HttpClient())
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            self.assertIn("missing id_str", str(ctx.exception))
        finally:
            _support.restore_http()

    def test_non_200_is_reported_with_status(self):
        _support.install_fake_http({"cdn.syndication.twimg.com": (429, "slow down")})
        try:
            provider = x2md.SyndicationProvider(x2md.HttpClient())
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            self.assertEqual(ctx.exception.status, 429)
            self.assertIn("HTTP 429", ctx.exception.describe())
        finally:
            _support.restore_http()


class TestFxTwitterProvider(unittest.TestCase):
    def tearDown(self):
        _support.restore_http()

    def test_thread_endpoint_is_preferred(self):
        fake = _support.install_fake_http(
            {"api.fxtwitter.com/2/thread/": "fxtwitter_v2_thread5.json"}
        )
        provider = x2md.FxTwitterProvider(x2md.HttpClient())
        doc = provider.fetch(x2md.parse_target("2072439205213421694"))
        self.assertEqual(doc.kind, "thread")
        self.assertTrue(any("/2/thread/" in url for url in fake.urls()))

    def test_falls_back_to_status_endpoint_when_thread_listing_is_empty(self):
        fake = _support.install_fake_http(
            {
                "api.fxtwitter.com/2/thread/20": '{"code":200,"status":{},"thread":[]}',
                "api.fxtwitter.com/2/status/20": "fxtwitter_v2_status_simple.json",
            }
        )
        provider = x2md.FxTwitterProvider(x2md.HttpClient())
        doc = provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
        self.assertEqual(doc.kind, "post")
        self.assertTrue(any("/2/status/20" in url for url in fake.urls()))

    def test_error_code_in_the_body_is_raised(self):
        _support.install_fake_http(
            {"api.fxtwitter.com": (200, '{"code":404,"message":"NOT_FOUND","tweet":null}')}
        )
        provider = x2md.FxTwitterProvider(x2md.HttpClient())
        with self.assertRaises(x2md.ProviderError) as ctx:
            provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
        self.assertIn("NOT_FOUND", str(ctx.exception))

    def test_handleless_requests_are_supported(self):
        _support.install_fake_http(
            {"api.fxtwitter.com": "fxtwitter_v2_status_simple.json"}
        )
        provider = x2md.FxTwitterProvider(x2md.HttpClient())
        doc = provider.fetch(x2md.parse_target("20"))
        self.assertEqual(doc.primary.post_id, "20")


class TestGraphQLProvider(unittest.TestCase):
    """The GraphQL path is implemented but NOT verified against live traffic."""

    def test_available_reports_missing_query_id(self):
        provider = x2md.GraphQLProvider(x2md.HttpClient(), {})
        reason = provider.available()
        self.assertIsNotNone(reason)
        self.assertIn("query id", reason)

    def test_available_when_query_id_is_configured(self):
        provider = x2md.GraphQLProvider(x2md.HttpClient(), {"query_id": "123456"})
        self.assertIsNone(provider.available())

    def test_missing_query_id_raises_a_clear_provider_error(self):
        provider = x2md.GraphQLProvider(x2md.HttpClient(), {})
        with self.assertRaises(x2md.ProviderError) as ctx:
            provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
        self.assertIn("query id", str(ctx.exception))

    def test_env_var_supplies_the_query_id(self):
        os.environ["X2MD_GRAPHQL_QUERY_ID"] = "999"
        try:
            provider = x2md.GraphQLProvider(x2md.HttpClient(), {})
            self.assertIsNone(provider.available())
        finally:
            del os.environ["X2MD_GRAPHQL_QUERY_ID"]

    def test_guest_activation_sends_the_authorization_header(self):
        # Regression: omitting the Bearer header made X answer HTTP 403 for
        # /1.1/guest/activate.json. Verified counterfactually against the live
        # endpoint (no header -> 403, header -> 200).
        fake = _support.install_fake_http(
            {
                "guest/activate.json": (200, '{"guest_token":"123"}'),
                "api.x.com/graphql": (404, "{}"),
            }
        )
        try:
            provider = x2md.GraphQLProvider(x2md.HttpClient(), {"query_id": "1"})
            with self.assertRaises(x2md.ProviderError):
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            activation = [
                call for call in fake.calls if "guest/activate.json" in call["url"]
            ]
            self.assertEqual(len(activation), 1)
            authorization = activation[0]["headers"].get("Authorization")
            self.assertTrue(authorization)
            self.assertTrue(authorization.startswith("Bearer "))
        finally:
            _support.restore_http()

    def test_graphql_request_carries_the_guest_token(self):
        fake = _support.install_fake_http(
            {
                "guest/activate.json": (200, '{"guest_token":"gt-999"}'),
                "api.x.com/graphql": (404, "{}"),
            }
        )
        try:
            provider = x2md.GraphQLProvider(x2md.HttpClient(), {"query_id": "1"})
            with self.assertRaises(x2md.ProviderError):
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            graphql_calls = [c for c in fake.calls if "api.x.com/graphql" in c["url"]]
            self.assertEqual(len(graphql_calls), 1)
            self.assertEqual(graphql_calls[0]["headers"].get("x-guest-token"), "gt-999")
        finally:
            _support.restore_http()

    def test_guest_token_activation_failure_is_reported(self):
        _support.install_fake_http(
            {"guest/activate.json": (403, '{"errors":[{"message":"forbidden"}]}')}
        )
        try:
            provider = x2md.GraphQLProvider(x2md.HttpClient(), {"query_id": "1"})
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            self.assertEqual(ctx.exception.status, 403)
        finally:
            _support.restore_http()

    def test_stale_query_id_404_is_reported(self):
        _support.install_fake_http(
            {
                "guest/activate.json": (200, '{"guest_token":"123"}'),
                "api.x.com/graphql": (404, '{"errors":[{"message":"does not exist"}]}'),
            }
        )
        try:
            provider = x2md.GraphQLProvider(x2md.HttpClient(), {"query_id": "1"})
            with self.assertRaises(x2md.ProviderError) as ctx:
                provider.fetch(x2md.parse_target("https://x.com/jack/status/20"))
            message = str(ctx.exception)
            self.assertEqual(ctx.exception.status, 404)
            self.assertIn("stale", message)
        finally:
            _support.restore_http()

    def test_normalizer_handles_the_documented_response_shape(self):
        # Offline coverage for the normalizer only. The live path is unverified.
        payload = _support.load_fixture("graphql_tweetdetail_synthetic.json")
        doc = x2md._document_from_graphql_payload(
            payload, x2md.parse_target("https://x.com/alice/status/1001"), "graphql"
        )
        self.assertEqual(doc.kind, "thread")
        self.assertEqual([p.post_id for p in doc.posts], ["1001", "1002"])
        self.assertEqual(doc.primary.author.handle, "alice")
        self.assertEqual(doc.primary.likes, 10)
        self.assertEqual(doc.primary.views, 500)
        self.assertTrue(doc.posts[1].is_self_reply)
        self.assertFalse(doc.posts[0].is_self_reply)

    def test_normalizer_rejects_a_payload_with_no_entries(self):
        with self.assertRaises(x2md.ProviderError) as ctx:
            x2md._document_from_graphql_payload(
                {"data": {"threaded_conversation_with_injections_v2": {"instructions": []}}},
                x2md.parse_target("https://x.com/alice/status/1001"),
                "graphql",
            )
        self.assertIn("no tweet entries", str(ctx.exception))


class TestUserAgent(unittest.TestCase):
    """The default User-Agent must not impersonate a browser.

    Measured 2026-09-18: a Chrome User-Agent makes api.vxtwitter.com answer HTTP
    403, while any honest User-Agent answers HTTP 200.
    """

    def test_default_user_agent_does_not_claim_to_be_a_browser(self):
        ua = x2md.DEFAULT_UA
        self.assertNotIn("Mozilla", ua)
        self.assertNotIn("AppleWebKit", ua)
        self.assertIn("x2md", ua)

    def test_client_uses_the_default_user_agent(self):
        client = x2md.HttpClient()
        self.assertEqual(client.user_agent, x2md.DEFAULT_UA)

    def test_client_user_agent_is_overridable(self):
        client = x2md.HttpClient(user_agent="custom/1")
        self.assertEqual(client.user_agent, "custom/1")

    def test_cli_exposes_a_user_agent_flag(self):
        parser = x2md.build_parser()
        args = parser.parse_args(["https://x.com/jack/status/20", "--user-agent", "ua/2"])
        self.assertEqual(args.user_agent, "ua/2")


class TestProviderRegistry(unittest.TestCase):
    def test_auto_expands_to_the_full_chain_in_order(self):
        providers = x2md.build_providers("auto", x2md.HttpClient(), {})
        self.assertEqual(
            [p.name for p in providers],
            ["fxtwitter", "vxtwitter", "syndication", "graphql"],
        )

    def test_explicit_provider_selects_exactly_one(self):
        providers = x2md.build_providers("syndication", x2md.HttpClient(), {})
        self.assertEqual([p.name for p in providers], ["syndication"])

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(x2md.InputError):
            x2md.build_providers("carrier-pigeon", x2md.HttpClient(), {})

    def test_thread_capabilities_are_declared_accurately(self):
        by_name = {
            cls.name: cls for cls in x2md.PROVIDER_CLASSES
        }
        self.assertTrue(by_name["fxtwitter"].supports_threads)
        self.assertTrue(by_name["graphql"].supports_threads)
        self.assertFalse(by_name["vxtwitter"].supports_threads)
        self.assertFalse(by_name["syndication"].supports_threads)


class _OkBody:
    """Minimal stand-in for the object returned by ``urlopen`` (a context manager)."""

    def __init__(self, payload):
        self._payload = payload
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self._payload

    def getcode(self):
        return 200


class TestHttpRetry(unittest.TestCase):
    """429 handling must back off and retry a bounded number of times.

    These patch ``urlopen`` rather than ``HttpClient.request``, because the retry
    loop lives inside ``request``: replacing ``request`` would test the stub.
    """

    def setUp(self):
        import urllib.request

        self.urlopen = urllib.request.urlopen
        self.calls = {"n": 0}

    def tearDown(self):
        import urllib.request

        urllib.request.urlopen = self.urlopen

    def _install(self, behaviour):
        import urllib.request

        def fake_urlopen(request, timeout=None):
            self.calls["n"] += 1
            return behaviour(self.calls["n"], request)

        urllib.request.urlopen = fake_urlopen

    def test_429_is_retried_then_succeeds(self):
        import urllib.error

        def behaviour(n, request):
            if n == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "slow down", {"Retry-After": "0"}, None
                )
            return _OkBody(b"{}")

        self._install(behaviour)
        client = x2md.HttpClient(max_retries=2, backoff=0.0)
        response = client.request("https://example.com/x")
        self.assertEqual(response.status, 200)
        self.assertEqual(self.calls["n"], 2)

    def test_retries_are_bounded(self):
        import urllib.error

        def behaviour(n, request):
            raise urllib.error.HTTPError(
                request.full_url, 429, "slow down", {"Retry-After": "0"}, None
            )

        self._install(behaviour)
        client = x2md.HttpClient(max_retries=2, backoff=0.0)
        response = client.request("https://example.com/x")
        self.assertEqual(response.status, 429)
        self.assertEqual(self.calls["n"], 3)  # initial + 2 retries, then give up

    def test_5xx_is_retried(self):
        import urllib.error

        def behaviour(n, request):
            if n == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 503, "unavailable", {}, None
                )
            return _OkBody(b'{"ok":true}')

        self._install(behaviour)
        client = x2md.HttpClient(max_retries=2, backoff=0.0)
        response = client.request("https://example.com/x")
        self.assertEqual(response.status, 200)
        self.assertEqual(self.calls["n"], 2)

    def test_404_is_not_retried(self):
        import urllib.error

        def behaviour(n, request):
            raise urllib.error.HTTPError(request.full_url, 404, "nope", {}, None)

        self._install(behaviour)
        client = x2md.HttpClient(max_retries=2, backoff=0.0)
        response = client.request("https://example.com/x")
        self.assertEqual(response.status, 404)
        self.assertEqual(self.calls["n"], 1)

    def test_network_error_is_retried_then_reported(self):
        import urllib.error

        def behaviour(n, request):
            raise urllib.error.URLError("dns failure")

        self._install(behaviour)
        client = x2md.HttpClient(max_retries=2, backoff=0.0)
        with self.assertRaises(x2md.ProviderError) as ctx:
            client.request("https://example.com/x", provider="p")
        self.assertIn("network error", str(ctx.exception))
        self.assertEqual(self.calls["n"], 3)

    def test_retry_after_is_capped(self):
        client = x2md.HttpClient()
        self.assertEqual(client._retry_delay({"retry-after": "9999"}, 1), 15.0)

    def test_retry_after_absent_uses_backoff(self):
        client = x2md.HttpClient(backoff=1.5)
        self.assertEqual(client._retry_delay({}, 2), 3.0)


if __name__ == "__main__":
    unittest.main()
