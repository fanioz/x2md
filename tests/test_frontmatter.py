"""YAML frontmatter content and robustness against adversarial post text."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


def document_for(fixture_name, target_id, provider="fxtwitter"):
    payload = _support.load_fixture(fixture_name)
    if provider == "fxtwitter":
        return x2md._document_from_fxtwitter_payload(
            payload, x2md.parse_target(target_id), provider
        )
    if provider == "vxtwitter":
        return x2md._document_from_vxtwitter_payload(
            payload, x2md.parse_target(target_id), provider
        )
    if provider == "syndication":
        return x2md._document_from_syndication_payload(
            payload, x2md.parse_target(target_id), provider
        )
    raise AssertionError(provider)


class TestRequiredFields(unittest.TestCase):
    def setUp(self):
        self.doc = document_for(
            "fxtwitter_v2_status_simple.json", "https://x.com/jack/status/20"
        )
        self.markdown = x2md.render_document(self.doc)
        self.front = _support.parse_frontmatter(self.markdown)

    def test_frontmatter_is_the_first_thing_in_the_document(self):
        self.assertTrue(self.markdown.startswith("---\n"))

    def test_all_required_keys_are_present(self):
        for key in (
            "source",
            "tweet_id",
            "author_name",
            "author_handle",
            "author_url",
            "posted_at",
            "kind",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.front)

    def test_values_match_the_source_post(self):
        self.assertEqual(self.front["tweet_id"], "20")
        self.assertEqual(self.front["author_name"], "jack")
        self.assertEqual(self.front["author_handle"], "jack")
        self.assertEqual(self.front["author_url"], "https://x.com/jack")
        self.assertEqual(self.front["source"], "https://x.com/jack/status/20")
        self.assertEqual(self.front["kind"], "post")

    def test_posted_at_is_iso8601(self):
        import datetime

        parsed = datetime.datetime.fromisoformat(self.front["posted_at"])
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.year, 2006)

    def test_stats_are_included_when_present(self):
        for key in ("likes", "retweets", "replies", "quotes", "bookmarks"):
            with self.subTest(key=key):
                self.assertIn(key, self.front)
                self.assertIsInstance(self.front[key], int)

    def test_absent_stats_are_omitted_not_nulled(self):
        # The syndication payload carries no retweet count, so the key must be
        # absent rather than present-and-null.
        doc = document_for(
            "syndication_status_simple.json",
            "https://x.com/jack/status/20",
            provider="syndication",
        )
        front = _support.parse_frontmatter(x2md.render_document(doc))
        self.assertIn("likes", front)
        self.assertNotIn("views", front)

    def test_thread_metadata_only_for_threads(self):
        self.assertNotIn("thread_length", self.front)
        thread = document_for(
            "fxtwitter_v2_thread5.json", "2072439205213421694"
        )
        front = _support.parse_frontmatter(x2md.render_document(thread))
        self.assertEqual(front["thread_length"], 5)
        self.assertTrue(front["thread_complete"])


class TestAdversarialInput(unittest.TestCase):
    """Post/author text must not be able to break the YAML or inject HTML."""

    def setUp(self):
        self.doc = document_for(
            "fxtwitter_v2_adversarial.json",
            "https://x.com/adv/status/1780000000000000002",
        )
        self.markdown = x2md.render_document(self.doc)
        self.front = _support.parse_frontmatter(self.markdown)
        self.body = _support.body_of(self.markdown)

    def test_frontmatter_still_parses(self):
        self.assertIsInstance(self.front, dict)

    def test_quotes_and_colons_survive_round_trip(self):
        self.assertIn('"The: Injector"', self.front["author_name"])

    def test_embedded_newline_is_escaped_not_literal(self):
        # A raw newline inside a value would start a new YAML line; the writer must
        # escape it. The parsed value keeps it, the raw block must not.
        self.assertIn("\n", self.front["author_name"])
        block = self.markdown[4 : self.markdown.index("\n---\n", 3)]
        for line in block.split("\n"):
            if line.startswith("author_name:"):
                self.assertIn("\\n", line)

    def test_adversarial_name_is_inert_data_not_markup(self):
        # The name legitimately appears verbatim inside the quoted YAML scalar --
        # that is *data*, quoted and escaped, not markup. What matters is that it
        # round-trips and that the rendered body contains no live tag.
        frontmatter = self.markdown[: self.markdown.index("\n---\n", 3)]
        self.assertIn("<script>", frontmatter)
        self.assertEqual(self.front["author_name"], '\u0045ve "The: Injector"\n</script><script>alert(2)</script>')
        self.assertNotIn("<script>", self.body)
        self.assertNotIn("</script>", self.body)
        self.assertNotIn("<script", self.body.replace("&lt;script", ""))

    def test_body_escapes_html_from_post_text(self):
        self.assertNotIn("<script>alert(1)</script>", self.body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.body)

    def test_yaml_escaping_rules_for_tricky_values(self):
        cases = {
            "plain": "hello",
            "colon": "key: value",
            "double quote": 'say "hi"',
            "single quote": "it's",
            "newline": "line1\nline2",
            "html": "<script>alert(1)</script>",
            "yaml doc marker": "---\nnext: 1",
            "leading dash": "- item",
            "hash": "a # not a comment",
            "null word": "null",
            "bool word": "true",
            "unicode separators": "a\u2028b\u2029c",
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                encoded = x2md.yaml_scalar(value)
                self.assertEqual(_json_load(encoded), value)

    def test_frontmatter_never_emits_a_bare_colon_line(self):
        block = self.markdown[4 : self.markdown.index("\n---\n", 3)]
        for line in block.split("\n"):
            self.assertRegex(line, r"^[A-Za-z_]+:")


def _json_load(text):
    import json

    return json.loads(text)


class TestSyndicationAndVxFrontmatter(unittest.TestCase):
    def test_vxtwitter_frontmatter(self):
        doc = document_for(
            "vxtwitter_status_simple.json",
            "https://x.com/jack/status/20",
            provider="vxtwitter",
        )
        front = _support.parse_frontmatter(x2md.render_document(doc))
        self.assertEqual(front["kind"], "post")
        self.assertEqual(front["tweet_id"], "20")
        self.assertEqual(front["author_handle"], "jack")
        self.assertEqual(front["provider"], "vxtwitter")

    def test_syndication_frontmatter(self):
        doc = document_for(
            "syndication_quote.json",
            "https://x.com/XCreators/status/2099922471272976442",
            provider="syndication",
        )
        front = _support.parse_frontmatter(x2md.render_document(doc))
        self.assertEqual(front["author_handle"], "XCreators")
        self.assertEqual(front["kind"], "post")


if __name__ == "__main__":
    unittest.main()
