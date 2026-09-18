"""Rich-text / facets / media / poll / quote to Markdown conversion."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


class TestFacetRendering(unittest.TestCase):
    """Facets must become links without letting post text inject markup."""

    def test_url_facet_becomes_inline_link_using_display_text(self):
        text = "read https://t.co/AbC123 now"
        facets = [
            {
                "type": "url",
                "indices": [5, 24],
                "original": "https://t.co/AbC123",
                "replacement": "https://example.com/a/b",
                "display": "example.com/a/b",
            }
        ]
        rendered = x2md.render_text_with_facets(text, facets)
        self.assertEqual(rendered, "read [example.com/a/b](https://example.com/a/b) now")

    def test_url_facet_identical_target_uses_autolink(self):
        text = "see https://example.com/x"
        facets = [
            {
                "type": "url",
                "indices": [4, 25],
                "original": "https://example.com/x",
                "replacement": "https://example.com/x",
                "display": "https://example.com/x",
            }
        ]
        rendered = x2md.render_text_with_facets(text, facets)
        self.assertEqual(rendered, "see <https://example.com/x>")

    def test_media_facet_is_removed(self):
        # Media facets are placeholders for the attached media, which is rendered
        # separately, so the pic.x.com stub is dropped.
        text = "hello pic.x.com/abc"
        facets = [{"type": "media", "indices": [6, 19]}]
        self.assertEqual(x2md.render_text_with_facets(text, facets), "hello ")

    def test_out_of_range_media_facet_is_ignored(self):
        # Regression: live fxtwitter payloads contain media facets whose indices
        # exceed the text length entirely. They must not corrupt the output.
        text = "short text"
        facets = [{"type": "media", "indices": [127, 150]}]
        self.assertEqual(x2md.render_text_with_facets(text, facets), "short text")

    def test_hashtag_mention_and_cashtag_left_readable(self):
        text = "hi @jack #tag $CASH"
        facets = [
            {"type": "mention", "indices": [3, 8]},
            {"type": "hashtag", "indices": [9, 13]},
        ]
        self.assertEqual(x2md.render_text_with_facets(text, facets), "hi @jack #tag $CASH")

    def test_html_in_post_text_is_escaped(self):
        text = "<script>alert(1)</script>"
        rendered = x2md.render_text_with_facets(text, [])
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_ampersand_escaped_exactly_once(self):
        rendered = x2md.render_text_with_facets("AT&T & Co", [])
        self.assertEqual(rendered, "AT&amp;T &amp; Co")

    def test_facet_link_target_with_parenthesis_is_encoded(self):
        text = "look https://t.co/x"
        facets = [
            {
                "type": "url",
                "indices": [5, 18],
                "replacement": "https://example.com/a_(b)",
                "display": "example.com",
            }
        ]
        rendered = x2md.render_text_with_facets(text, facets)
        self.assertIn("(https://example.com/a_%28b%29)", rendered)

    def test_malformed_facets_do_not_raise(self):
        text = "some text"
        for bad in (
            None,
            [None],
            [{}],
            [{"type": "url"}],
            [{"type": "url", "indices": "nope"}],
            [{"type": "url", "indices": [1]}],
            [{"type": "url", "indices": [-5, 4], "replacement": "https://e.com"}],
            [{"type": "url", "indices": [2, 999], "replacement": "https://e.com"}],
        ):
            with self.subTest(facets=bad):
                self.assertIsInstance(
                    x2md.render_text_with_facets(text, bad or []), str
                )


class TestImageUrlUpgrade(unittest.TestCase):
    """Media links must point at the highest available resolution."""

    def test_name_parameter_is_upgraded_to_orig(self):
        self.assertEqual(
            x2md.upgrade_image_url("https://pbs.twimg.com/media/ABC.jpg?name=small"),
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
        )

    def test_name_among_other_parameters(self):
        self.assertEqual(
            x2md.upgrade_image_url(
                "https://pbs.twimg.com/media/A.jpg?format=jpg&name=medium"
            ),
            "https://pbs.twimg.com/media/A.jpg?format=jpg&name=orig",
        )

    def test_bare_media_url_gains_orig(self):
        self.assertEqual(
            x2md.upgrade_image_url("https://pbs.twimg.com/media/ABC.jpg"),
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
        )

    def test_already_orig_is_unchanged(self):
        url = "https://pbs.twimg.com/media/ABC.jpg?name=orig"
        self.assertEqual(x2md.upgrade_image_url(url), url)

    def test_non_twimg_url_untouched(self):
        url = "https://example.com/x.jpg?name=small"
        self.assertEqual(x2md.upgrade_image_url(url), url)


class TestMediaRendering(unittest.TestCase):
    def test_image_renders_with_alt_text_and_orig_url(self):
        lines = x2md.render_media_list(
            [x2md.Media(kind="image", url="https://pbs.twimg.com/media/A.jpg?name=orig", alt="a cat")]
        )
        self.assertIn("- ![a cat](https://pbs.twimg.com/media/A.jpg?name=orig)", lines)

    def test_image_without_alt_gets_placeholder(self):
        lines = x2md.render_media_list(
            [x2md.Media(kind="image", url="https://pbs.twimg.com/media/A.jpg?name=orig")]
        )
        self.assertIn("- ![image](https://pbs.twimg.com/media/A.jpg?name=orig)", lines)

    def test_video_links_thumbnail_and_mp4(self):
        lines = x2md.render_media_list(
            [
                x2md.Media(
                    kind="video",
                    url="https://pbs.twimg.com/thumb.jpg",
                    width=1920,
                    height=1080,
                    video_url="https://video.twimg.com/v.mp4",
                    duration=39.2,
                )
            ]
        )
        joined = "\n".join(lines)
        self.assertIn("[Video thumbnail](https://pbs.twimg.com/thumb.jpg)", joined)
        self.assertIn("[Video file](https://video.twimg.com/v.mp4)", joined)
        self.assertIn("1920x1080", joined)
        self.assertIn("39.2s", joined)

    def test_alt_text_cannot_inject_markup(self):
        # The alt text tries to close the image label early and start a second
        # link. Escaping "]" keeps the label intact, so exactly one link target is
        # emitted and the tag stays inert text.
        lines = x2md.render_media_list(
            [
                x2md.Media(
                    kind="image",
                    url="https://pbs.twimg.com/media/A.jpg?name=orig",
                    alt="x](https://evil.example) <script>",
                )
            ]
        )
        joined = "\n".join(lines)
        # Exactly one *unescaped* "](" may appear: the real link. The "]" inside the
        # alt text is escaped, so it cannot terminate the label early. The hostile
        # URL survives only as inert label text, which is the correct outcome.
        self.assertEqual(len(re.findall(r"(?<!\\)\]\(", joined)), 1)
        self.assertIn("\\]", joined)
        self.assertNotIn("<script>", joined)
        self.assertIn("](https://pbs.twimg.com/media/A.jpg?name=orig)", joined)

    def test_empty_media_renders_nothing(self):
        self.assertEqual(x2md.render_media_list([]), [])


class TestPollRendering(unittest.TestCase):
    def test_poll_lists_options_with_percentages(self):
        poll = x2md.Poll(
            choices=[
                x2md.PollChoice(label="CommonMark", count=558, percentage=45.2),
                x2md.PollChoice(label="GFM", count=676, percentage=54.8),
            ],
            total_votes=1234,
            ends_at="2026-03-11T10:15:30+00:00",
        )
        lines = x2md.render_poll(poll)
        joined = "\n".join(lines)
        self.assertIn("1,234 votes", joined)
        self.assertIn("- CommonMark — 45.2%, 558 votes", lines)
        self.assertIn("- GFM — 54.8%, 676 votes", lines)

    def test_poll_label_is_escaped(self):
        poll = x2md.Poll(
            choices=[x2md.PollChoice(label="<b>x</b>", count=1, percentage=1.0)],
            total_votes=1,
        )
        joined = "\n".join(x2md.render_poll(poll))
        self.assertNotIn("<b>", joined)
        self.assertIn("&lt;b&gt;", joined)

    def test_empty_poll_renders_nothing(self):
        self.assertEqual(x2md.render_poll(x2md.Poll()), [])


class TestQuoteRendering(unittest.TestCase):
    def _quote(self):
        author = x2md.Author(name="Grok", handle="grok", url="https://x.com/grok")
        return x2md.Post(
            post_id="999",
            url="https://x.com/grok/status/999",
            text="quoted body",
            created_at="2026-09-15T15:02:09+00:00",
            author=author,
        )

    def test_quote_is_a_blockquote_with_attribution(self):
        lines = x2md.render_quote(self._quote())
        joined = "\n".join(lines)
        self.assertTrue(all(line.startswith(">") for line in lines))
        self.assertIn("> **Grok (@grok)** — 2026-09-15T15:02:09+00:00", joined)
        self.assertIn("> quoted body", joined)

    def test_nested_quote_deepens_the_blockquote(self):
        inner = self._quote()
        outer = self._quote()
        outer.post_id = "1000"
        outer.quote = inner
        joined = "\n".join(x2md.render_quote(outer))
        self.assertIn("> > **Grok (@grok)**", joined)

    def test_quote_media_is_rendered_inside_the_blockquote(self):
        quote = self._quote()
        quote.media = [
            x2md.Media(kind="image", url="https://pbs.twimg.com/media/Q.jpg?name=orig")
        ]
        joined = "\n".join(x2md.render_quote(quote))
        self.assertIn("> - ![image](https://pbs.twimg.com/media/Q.jpg?name=orig)", joined)

    def test_none_quote_renders_nothing(self):
        self.assertEqual(x2md.render_quote(None), [])


class TestLineBreaks(unittest.TestCase):
    """Line breaks must survive rendering without emitting stray backslashes."""

    def test_single_newline_gets_a_hard_break_marker(self):
        self.assertEqual(x2md.hard_breaks("a\nb"), "a\\\nb")

    def test_blank_line_is_left_alone(self):
        self.assertEqual(x2md.hard_breaks("a\n\nb"), "a\n\nb")

    def test_no_stray_backslash_line_for_paragraph_break(self):
        rendered = x2md.hard_breaks("one\n\ntwo")
        self.assertNotIn("\n\\\n", rendered)
        for line in rendered.split("\n"):
            self.assertNotEqual(line.strip(), "\\")

    def test_trailing_newline_not_marked(self):
        self.assertEqual(x2md.hard_breaks("a\n"), "a\n")

    def test_crlf_is_normalised(self):
        self.assertEqual(x2md.hard_breaks("a\r\nb"), "a\\\nb")

    def test_existing_backslash_not_doubled(self):
        self.assertEqual(x2md.hard_breaks("a\\\nb"), "a\\\nb")

    def test_single_line_collapses_whitespace(self):
        self.assertEqual(x2md.single_line("Eve\n<script>\t x"), "Eve <script> x")


if __name__ == "__main__":
    unittest.main()
