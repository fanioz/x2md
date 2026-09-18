"""Long-form X Article rendering: Draft.js blocks and entities to Markdown."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _support  # noqa: E402

x2md = _support.x2md


def article_document(fixture_name, status_id):
    payload = _support.load_fixture(fixture_name)
    return x2md._document_from_fxtwitter_payload(
        payload, x2md.parse_target(status_id), "fxtwitter"
    )


class TestArticleDetection(unittest.TestCase):
    def test_long_form_post_is_kind_article(self):
        doc = article_document(
            "fxtwitter_v2_article.json", "https://x.com/XBusiness/status/2097390372670575039"
        )
        self.assertEqual(doc.kind, "article")
        self.assertIsNotNone(doc.primary.article)

    def test_frontmatter_kind_is_article(self):
        doc = article_document(
            "fxtwitter_v2_article.json", "https://x.com/XBusiness/status/2097390372670575039"
        )
        front = _support.parse_frontmatter(x2md.render_document(doc))
        self.assertEqual(front["kind"], "article")

    def test_plain_post_has_no_article(self):
        payload = _support.load_fixture("fxtwitter_v2_status_simple.json")
        doc = x2md._document_from_fxtwitter_payload(
            payload, x2md.parse_target("20"), "fxtwitter"
        )
        self.assertIsNone(doc.primary.article)


class TestArticleStructure(unittest.TestCase):
    """The body must be real Markdown structure, not a truncated snippet."""

    def setUp(self):
        self.doc = article_document(
            "fxtwitter_v2_article.json", "https://x.com/XBusiness/status/2097390372670575039"
        )
        self.article = self.doc.primary.article
        self.markdown = x2md.render_document(self.doc)
        self.body = _support.body_of(self.markdown)

    def test_title_becomes_an_h1(self):
        self.assertIn("# %s" % self.article.title, self.markdown)

    def test_every_block_is_rendered(self):
        # 42 blocks, of which 14 are atomic embedded-post references.
        self.assertEqual(len(self.article.blocks), 42)
        self.assertEqual(self.body.count("> **Embedded post**"), 14)

    def test_header_two_blocks_become_h3(self):
        header_texts = [
            block.text
            for block in self.article.blocks
            if block.type == "header-two"
        ]
        self.assertTrue(header_texts)
        for text in header_texts:
            self.assertIn("### %s" % text, self.body)

    def test_unordered_list_items_become_bullets(self):
        items = [
            block.text
            for block in self.article.blocks
            if block.type == "unordered-list-item"
        ]
        self.assertTrue(items)
        for text in items:
            self.assertIn("- %s" % text, self.body)

    def test_embedded_posts_are_linked(self):
        tweet_entities = [
            entry
            for entry in self.article.entity_map
            if entry["value"]["type"] == "TWEET"
        ]
        self.assertEqual(len(tweet_entities), 14)
        first_id = tweet_entities[0]["value"]["data"]["tweetId"]
        self.assertIn("https://x.com/i/status/%s" % first_id, self.body)

    def test_cover_image_is_rendered_at_full_resolution(self):
        self.assertIsNotNone(self.article.cover)
        self.assertIn("name=orig", self.article.cover.url)
        self.assertIn("![cover image](%s)" % self.article.cover.url, self.body)

    def test_preview_text_is_rendered(self):
        self.assertIn("> %s" % self.article.preview_text, self.body)


class TestArticleMediaAndLinks(unittest.TestCase):
    def setUp(self):
        self.doc = article_document(
            "fxtwitter_v2_article_media.json",
            "https://x.com/XCreators/status/2085835082166653393",
        )
        self.article = self.doc.primary.article
        self.body = _support.body_of(x2md.render_document(self.doc))

    def test_media_entities_resolve_to_image_links(self):
        # 6 MEDIA entities, all ApiImage, resolved through media_entities.
        self.assertEqual(len(self.article.media_entities), 6)
        for entry in self.article.media_entities:
            self.assertIn(
                "![image](%s)" % x2md.upgrade_image_url(entry["media_info"]["original_img_url"]),
                self.body,
            )

    def test_entity_map_is_not_in_key_order(self):
        # Regression guard: the live payload stores entityMap as a permutation of
        # the key values. If a future payload happened to be in key order this test
        # would stop protecting anything, so assert the precondition explicitly.
        keys = [int(entry["key"]) for entry in self.article.entity_map]
        self.assertNotEqual(keys, list(range(len(keys))))

    def test_link_labels_pair_with_the_correct_url(self):
        # Before the key/position bug was fixed, labels were paired with the wrong
        # URLs because entityMap was indexed by array position.
        by_key = x2md.entity_map_by_key(self.article.entity_map)
        checked = 0
        for block in self.article.blocks:
            for rng in block.entity_ranges or []:
                entity = by_key.get(rng["key"])
                if not entity or entity["value"]["type"] != "LINK":
                    continue
                label = block.text[rng["offset"] : rng["offset"] + rng["length"]].strip()
                url = entity["value"]["data"]["url"]
                if not label:
                    continue
                expected = "[%s](%s)" % (
                    x2md.escape_markdown_link_text(label),
                    x2md.escape_markdown_url(url),
                )
                with self.subTest(label=label):
                    self.assertIn(expected, self.body)
                checked += 1
        self.assertGreater(checked, 5)

    def test_known_label_url_pairings_are_semantically_right(self):
        pairs = {
            "Community Guidelines": "x-rules",
            "Terms of Service": "x.com/en/tos",
        }
        for label, url_fragment in pairs.items():
            with self.subTest(label=label):
                index = self.body.index("[%s](" % label)
                snippet = self.body[index : index + 160]
                self.assertIn(url_fragment, snippet)

    def test_blank_anchor_links_become_autolinks(self):
        # Some LINK entities are anchored to a single space; an empty label would
        # render as "[](...)", so the target is emitted as a bare autolink.
        self.assertNotIn("[](http", self.body)
        self.assertNotIn("[ ](", self.body)


class TestArticleBlockTypes(unittest.TestCase):
    """Block-type dispatch, including types absent from the captured fixtures."""

    def _render(self, blocks, entity_map=None, media_entities=None):
        article = x2md.Article(
            title="T",
            blocks=blocks,
            entity_map=entity_map or [],
            media_entities=media_entities or [],
        )
        return "\n".join(x2md.render_article(article))

    def test_header_one_and_two(self):
        out = self._render(
            [
                x2md.ArticleBlock(type="header-one", text="One"),
                x2md.ArticleBlock(type="header-two", text="Two"),
            ]
        )
        self.assertIn("## One", out)
        self.assertIn("### Two", out)

    def test_ordered_list_is_numbered_sequentially(self):
        out = self._render(
            [
                x2md.ArticleBlock(type="ordered-list-item", text="first"),
                x2md.ArticleBlock(type="ordered-list-item", text="second"),
                x2md.ArticleBlock(type="ordered-list-item", text="third"),
            ]
        )
        self.assertIn("1. first", out)
        self.assertIn("2. second", out)
        self.assertIn("3. third", out)

    def test_blockquote_block(self):
        out = self._render([x2md.ArticleBlock(type="blockquote", text="quoted")])
        self.assertIn("> quoted", out)

    def test_code_block_is_fenced(self):
        out = self._render([x2md.ArticleBlock(type="code-block", text="x = 1")])
        self.assertIn("```\nx = 1\n```", out)

    def test_divider_entity(self):
        entity_map = [{"key": "0", "value": {"type": "DIVIDER", "data": {}}}]
        out = self._render(
            [
                x2md.ArticleBlock(
                    type="atomic",
                    text=" ",
                    entity_ranges=[{"key": 0, "length": 1, "offset": 0}],
                )
            ],
            entity_map=entity_map,
        )
        self.assertIn("---", out)

    def test_markdown_entity_keeps_syntax_but_neutralises_html(self):
        entity_map = [
            {
                "key": "0",
                "value": {
                    "type": "MARKDOWN",
                    "data": {"markdown": "| a | b |\n|---|---|\n| 1 | 2 |<script>x</script>"},
                },
            }
        ]
        out = self._render(
            [
                x2md.ArticleBlock(
                    type="unstyled",
                    text=" ",
                    entity_ranges=[{"key": 0, "length": 1, "offset": 0}],
                )
            ],
            entity_map=entity_map,
        )
        self.assertIn("| a | b |", out)
        self.assertNotIn("<script>", out)

    def test_media_entity_of_unknown_id_is_skipped_safely(self):
        entity_map = [
            {
                "key": "0",
                "value": {
                    "type": "MEDIA",
                    "data": {"mediaItems": [{"mediaId": "missing", "localMediaId": "1"}]},
                },
            }
        ]
        out = self._render(
            [
                x2md.ArticleBlock(
                    type="atomic",
                    text=" ",
                    entity_ranges=[{"key": 0, "length": 1, "offset": 0}],
                )
            ],
            entity_map=entity_map,
            media_entities=[],
        )
        self.assertEqual(out.strip(), "")

    def test_unknown_block_type_is_treated_as_paragraph(self):
        out = self._render([x2md.ArticleBlock(type="something-new", text="hello")])
        self.assertIn("hello", out)

    def test_blank_paragraphs_are_not_emitted(self):
        out = self._render([x2md.ArticleBlock(type="unstyled", text="   ")])
        self.assertEqual(out.strip(), "")

    def test_article_text_is_html_escaped(self):
        out = self._render(
            [x2md.ArticleBlock(type="unstyled", text="<img src=x onerror=alert(1)>")]
        )
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img", out)


if __name__ == "__main__":
    unittest.main()
