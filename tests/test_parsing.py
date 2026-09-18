"""URL / status-id parsing for every accepted input form."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


class TestAcceptedForms(unittest.TestCase):
    """Every documented input shape must resolve to the same status id."""

    ID = "2072439205213421694"

    def test_bare_numeric_id(self):
        target = x2md.parse_target(self.ID)
        self.assertEqual(target.status_id, self.ID)
        self.assertIsNone(target.handle)
        self.assertFalse(target.from_url)

    def test_short_numeric_id(self):
        # jack's first post really is id 20, so short ids must not be rejected.
        self.assertEqual(x2md.parse_target("20").status_id, "20")

    def test_canonical_x_com(self):
        target = x2md.parse_target("https://x.com/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)
        self.assertEqual(target.handle, "XCreators")

    def test_twitter_com(self):
        target = x2md.parse_target("https://twitter.com/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)
        self.assertEqual(target.handle, "XCreators")

    def test_mobile_and_www_variants(self):
        for host in (
            "mobile.x.com",
            "www.x.com",
            "mobile.twitter.com",
            "www.twitter.com",
        ):
            with self.subTest(host=host):
                target = x2md.parse_target(
                    "https://%s/XCreators/status/%s" % (host, self.ID)
                )
                self.assertEqual(target.status_id, self.ID)
                self.assertEqual(target.handle, "XCreators")

    def test_scheme_is_optional(self):
        target = x2md.parse_target("x.com/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)

    def test_http_scheme(self):
        target = x2md.parse_target("http://x.com/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)

    def test_query_string_is_ignored(self):
        target = x2md.parse_target(
            "https://x.com/XCreators/status/%s?s=20&t=AbC-123_xyz" % self.ID
        )
        self.assertEqual(target.status_id, self.ID)
        self.assertEqual(target.handle, "XCreators")

    def test_fragment_is_ignored(self):
        target = x2md.parse_target(
            "https://x.com/XCreators/status/%s#m" % self.ID
        )
        self.assertEqual(target.status_id, self.ID)

    def test_trailing_slash(self):
        target = x2md.parse_target(
            "https://x.com/XCreators/status/%s/" % self.ID
        )
        self.assertEqual(target.status_id, self.ID)

    def test_i_web_status_form(self):
        target = x2md.parse_target("https://twitter.com/i/web/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)
        self.assertIsNone(target.handle)

    def test_i_status_form(self):
        target = x2md.parse_target("https://x.com/i/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)
        self.assertIsNone(target.handle)

    def test_statuses_plural_legacy_form(self):
        target = x2md.parse_target(
            "https://twitter.com/XCreators/statuses/" + self.ID
        )
        self.assertEqual(target.status_id, self.ID)
        self.assertEqual(target.handle, "XCreators")

    def test_media_suffix_form(self):
        target = x2md.parse_target(
            "https://x.com/XCreators/status/%s/photo/1" % self.ID
        )
        self.assertEqual(target.status_id, self.ID)
        self.assertEqual(target.handle, "XCreators")

    def test_video_suffix_form(self):
        target = x2md.parse_target(
            "https://x.com/XCreators/status/%s/video/1" % self.ID
        )
        self.assertEqual(target.status_id, self.ID)

    def test_article_path_form(self):
        target = x2md.parse_target("https://x.com/i/article/" + self.ID)
        self.assertEqual(target.status_id, self.ID)

    def test_uppercase_host(self):
        target = x2md.parse_target("https://X.COM/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)

    def test_port_in_host(self):
        target = x2md.parse_target("https://x.com:443/XCreators/status/" + self.ID)
        self.assertEqual(target.status_id, self.ID)

    def test_surrounding_whitespace(self):
        target = x2md.parse_target("  https://x.com/XCreators/status/%s \n" % self.ID)
        self.assertEqual(target.status_id, self.ID)


class TestRejectedForms(unittest.TestCase):
    """Malformed input must fail loudly with a helpful message."""

    def test_empty_string(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("")

    def test_whitespace_only(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("   ")

    def test_unsupported_host(self):
        with self.assertRaises(x2md.InputError) as ctx:
            x2md.parse_target("https://example.com/jack/status/20")
        self.assertIn("unsupported host", str(ctx.exception))

    def test_nitter_host_is_not_silently_accepted(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("https://nitter.net/jack/status/20")

    def test_url_without_status_path(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("https://x.com/jack")

    def test_status_without_id(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("https://x.com/jack/status")

    def test_non_numeric_id(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("https://x.com/jack/status/notanumber")

    def test_bare_word(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("hello")

    def test_deep_link_without_id(self):
        with self.assertRaises(x2md.InputError):
            x2md.parse_target("https://x.com/home")


class TestTargetUrls(unittest.TestCase):
    """Derived URLs must be well formed for both handle and handle-less input."""

    def test_handle_forms_canonical_url(self):
        target = x2md.parse_target("https://mobile.x.com/jack/status/20")
        self.assertEqual(target.canonical_url, "https://x.com/jack/status/20")

    def test_handleless_forms_canonical_url(self):
        target = x2md.parse_target("https://twitter.com/i/web/status/20")
        self.assertEqual(target.canonical_url, "https://x.com/i/status/20")

    def test_source_url_is_recorded_for_urls(self):
        target = x2md.parse_target("https://x.com/jack/status/20")
        self.assertTrue(target.from_url)
        self.assertIn("jack/status/20", target.display_url)

    def test_source_url_synthesised_for_bare_id(self):
        target = x2md.parse_target("20")
        self.assertEqual(target.display_url, "https://x.com/i/status/20")


if __name__ == "__main__":
    unittest.main()
