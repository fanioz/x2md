"""Thread detection, ordering, numbering and honest degradation."""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


class TestThreadAssembly(unittest.TestCase):
    def setUp(self):
        self.payload = _support.load_fixture("fxtwitter_v2_thread5.json")
        self.doc = x2md._document_from_fxtwitter_payload(
            self.payload,
            x2md.parse_target("https://x.com/XCreators/status/2072439205213421694"),
            "fxtwitter",
        )
        self.markdown = x2md.render_document(self.doc)

    def test_kind_is_thread(self):
        self.assertEqual(self.doc.kind, "thread")

    def test_all_posts_are_present_and_in_order(self):
        expected = [item["id"] for item in self.payload["thread"]]
        actual = [post.post_id for post in self.doc.posts]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 5)

    def test_posts_are_numbered_in_order(self):
        headings = [
            line
            for line in self.markdown.split("\n")
            if line.startswith("## ") and "/" in line
        ]
        self.assertEqual(
            headings, ["## 1/5", "## 2/5", "## 3/5", "## 4/5", "## 5/5"]
        )

    def test_numbering_appears_after_the_document_title(self):
        title_index = self.markdown.index("# Thread by")
        first_index = self.markdown.index("## 1/5")
        self.assertLess(title_index, first_index)

    def test_thread_is_marked_complete(self):
        self.assertTrue(self.doc.thread_complete)
        front = _support.parse_frontmatter(self.markdown)
        self.assertTrue(front["thread_complete"])

    def test_each_post_carries_its_own_permalink(self):
        for post in self.doc.posts:
            self.assertIn(post.url, self.markdown)

    def test_permalink_of_a_middle_post_resolves_to_the_thread(self):
        # Requesting post 2 of the thread must still yield the whole thread.
        doc = x2md._document_from_fxtwitter_payload(
            self.payload,
            x2md.parse_target("https://x.com/XCreators/status/2072439207402820041"),
            "fxtwitter",
        )
        self.assertEqual(doc.kind, "thread")
        self.assertEqual(len(doc.posts), 5)


class TestSinglePost(unittest.TestCase):
    def test_single_post_is_kind_post(self):
        payload = _support.load_fixture("fxtwitter_v2_status_simple.json")
        doc = x2md._document_from_fxtwitter_payload(
            payload, x2md.parse_target("https://x.com/jack/status/20"), "fxtwitter"
        )
        self.assertEqual(doc.kind, "post")
        self.assertEqual(len(doc.posts), 1)
        self.assertNotIn("## 1/1", x2md.render_document(doc))


class TestDegradationIsLabelled(unittest.TestCase):
    """A thread we cannot fully retrieve must say so, never look complete."""

    def test_vxtwitter_self_reply_is_flagged_incomplete(self):
        # vxtwitter cannot enumerate conversations; this post replies to its own
        # author, so the result must be labelled partial rather than passed off as
        # a complete thread.
        payload = _support.load_fixture("vxtwitter_status_simple.json")
        payload = dict(payload)
        payload["replyingToID"] = "19"
        payload["replyingTo"] = "jack"
        doc = x2md._document_from_vxtwitter_payload(
            payload, x2md.parse_target("https://x.com/jack/status/20"), "vxtwitter"
        )
        self.assertEqual(doc.kind, "thread")
        self.assertFalse(doc.thread_complete)
        self.assertTrue(doc.warnings)

        markdown = x2md.render_document(doc)
        front = _support.parse_frontmatter(markdown)
        self.assertFalse(front["thread_complete"])
        self.assertIn("incomplete", markdown.lower())

    def test_reply_to_another_author_is_not_treated_as_a_thread(self):
        payload = _support.load_fixture("vxtwitter_status_simple.json")
        payload = dict(payload)
        payload["replyingTo"] = "someoneelse"
        payload["replyingToID"] = "123"
        doc = x2md._document_from_vxtwitter_payload(
            payload, x2md.parse_target("https://x.com/jack/status/20"), "vxtwitter"
        )
        self.assertEqual(doc.kind, "post")
        self.assertTrue(doc.thread_complete)

    def test_single_post_provider_adds_a_thread_warning(self):
        # When a provider without conversation support is used, the caller is told
        # that the output is limited to the requested post.
        client = x2md.HttpClient()
        target = x2md.parse_target("https://x.com/jack/status/20")
        _support.install_fake_http(
            {"api.vxtwitter.com": "vxtwitter_status_simple.json"}
        )
        providers = x2md.build_providers("vxtwitter", client, {})
        document, errors = x2md.fetch_document(
            target, providers, client, debug=False, stream=io.StringIO()
        )
        self.assertEqual(errors, [])
        self.assertEqual(document.kind, "post")
        self.assertTrue(any("cannot enumerate threads" in w for w in document.warnings))

    def test_thread_payload_sets_self_reply_flags(self):
        payload = _support.load_fixture("fxtwitter_v2_thread5.json")
        doc = x2md._document_from_fxtwitter_payload(
            payload, x2md.parse_target("2072439205213421694"), "fxtwitter"
        )
        self.assertFalse(doc.posts[0].is_self_reply)
        for post in doc.posts[1:]:
            self.assertTrue(post.is_self_reply, post.post_id)


class TestProviderFallback(unittest.TestCase):
    """The chain must keep the real per-provider errors and try the next one."""

    def tearDown(self):
        x2md.HttpClient.request = _ORIGINAL_REQUEST

    def test_falls_through_to_the_next_provider(self):
        client = x2md.HttpClient()
        _support.install_fake_http(
            {
                "api.fxtwitter.com": (503, '{"code":503,"message":"upstream down"}'),
                "api.vxtwitter.com": "vxtwitter_status_simple.json",
                "cdn.syndication.twimg.com": "syndication_status_simple.json",
            }
        )
        providers = x2md.build_providers("auto", client, {})
        document, errors = x2md.fetch_document(
            x2md.parse_target("https://x.com/jack/status/20"),
            providers,
            client,
            debug=False,
            stream=io.StringIO(),
        )
        self.assertEqual(document.provider, "vxtwitter")
        self.assertTrue(errors)
        self.assertEqual(errors[0].provider, "fxtwitter")
        self.assertEqual(errors[0].status, 503)

    def test_all_providers_failing_reports_each_one(self):
        client = x2md.HttpClient()
        _support.install_fake_http(
            {
                "api.fxtwitter.com": (500, "boom"),
                "api.vxtwitter.com": (500, "boom"),
                "cdn.syndication.twimg.com": (500, "boom"),
            }
        )
        providers = x2md.build_providers("auto", client, {})
        with self.assertRaises(x2md.NoProviderAvailable) as ctx:
            x2md.fetch_document(
                x2md.parse_target("https://x.com/jack/status/20"),
                providers,
                client,
                debug=False,
                stream=io.StringIO(),
            )
        described = " ".join(err.describe() for err in ctx.exception.errors)
        self.assertIn("fxtwitter", described)
        self.assertIn("vxtwitter", described)
        self.assertIn("syndication", described)


_ORIGINAL_REQUEST = x2md.HttpClient.request

if __name__ == "__main__":
    unittest.main()
