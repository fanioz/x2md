"""Mapping layer between the Apify Actor runtime and the x2md.py core.

Stdlib only: the apify SDK (`async with Actor`, `push_data`, `set_value`,
proxy, logging) lives in ``main.py``. Everything here is pure and unit
tested offline via ``tests/test_actor.py``.

Decisions (from wayfinder tickets #4/#5/#6):
- input: ``startUrls`` (URLs or bare IDs, incl. requestListSources objects),
  ``maxItems`` (default 10, hard cap 50), ``provider`` (auto default with
  optional override), ``downloadMedia`` (granular images/videos/gifs/zip
  toggles, all off by default), ``outputFormat`` (flat/nested/both).
- output: one dataset item per URL — flat ``posts`` plus optional nested
  ``thread`` — with Markdown body, media refs incl. ``fileKey``, warnings,
  and ``provider`` + ``providerErrors``. Each post also carries ``poll``,
  ``quote``, and ``article`` verbatim from :func:`x2md.document_to_json`, so
  the Actor and ``x2md --json`` cannot disagree. Total failure yields a
  ``failedProviders`` chain instead.
- media keys: ``<prefix>_<handle>_<postid>_<timestamp>_p<index>.<ext>``.
  The Apify key-value store only accepts ``a-zA-Z0-9!-_. '()``, so ``/``
  is not a legal separator.
"""

import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import x2md

MAX_ITEMS_HARD_CAP = 50
DEFAULT_MAX_ITEMS = 10
#: Machine-readable warning code prepended to ``warnings`` when x2md could not
#: enumerate a whole self-thread. The prose warnings x2md emits explain *why*;
#: this code exists so consumers can filter without string matching.
WARNING_THREAD_INCOMPLETE = "thread_incomplete"
VALID_PROVIDERS = ("auto", "fxtwitter", "vxtwitter", "syndication", "graphql")
VALID_OUTPUT_FORMATS = ("flat", "nested", "both")
MEDIA_TOGGLES = ("images", "videos", "gifs", "zip")
KIND_TO_TOGGLE = {"image": "images", "video": "videos", "gif": "gifs"}


class ActorInputError(ValueError):
    """Raised when the Actor input fails validation."""


def error_to_dict(exc):
    """Serialize a provider failure for the dataset's error list."""
    return {
        "provider": exc.provider,
        "message": exc.message,
        "url": exc.url,
        "status": exc.status,
    }


def validate_input(raw):
    """Validate raw Actor input and return a cleaned dict with defaults."""
    if not isinstance(raw, dict):
        raise ActorInputError("Actor input must be a JSON object.")
    start_urls = raw.get("startUrls")
    if not isinstance(start_urls, list) or not start_urls:
        raise ActorInputError("'startUrls' must be a non-empty array.")
    cleaned_urls = []
    for entry in start_urls:
        if isinstance(entry, dict):
            entry = entry.get("url")
        if not isinstance(entry, str) or not entry.strip():
            raise ActorInputError("Each 'startUrls' entry must be a URL or ID string.")
        cleaned_urls.append(entry.strip())

    max_items = raw.get("maxItems", DEFAULT_MAX_ITEMS)
    if isinstance(max_items, bool) or not isinstance(max_items, int):
        raise ActorInputError("'maxItems' must be an integer.")
    if max_items < 1:
        raise ActorInputError("'maxItems' must be at least 1.")
    if max_items > MAX_ITEMS_HARD_CAP:
        raise ActorInputError(
            "'maxItems' cannot exceed %d (platform memory budget)." % MAX_ITEMS_HARD_CAP
        )

    provider = raw.get("provider", "auto")
    if provider not in VALID_PROVIDERS:
        raise ActorInputError(
            "'provider' must be one of: %s." % ", ".join(VALID_PROVIDERS)
        )

    toggles = raw.get("downloadMedia", {})
    if not isinstance(toggles, dict):
        raise ActorInputError("'downloadMedia' must be an object of booleans.")
    cleaned_toggles = {}
    for name in MEDIA_TOGGLES:
        value = toggles.get(name, False)
        if not isinstance(value, bool):
            raise ActorInputError("'downloadMedia.%s' must be a boolean." % name)
        cleaned_toggles[name] = value

    output_format = raw.get("outputFormat", "both")
    if output_format not in VALID_OUTPUT_FORMATS:
        raise ActorInputError(
            "'outputFormat' must be one of: %s." % ", ".join(VALID_OUTPUT_FORMATS)
        )

    return {
        "startUrls": cleaned_urls,
        "maxItems": max_items,
        "provider": provider,
        "downloadMedia": cleaned_toggles,
        "outputFormat": output_format,
    }


def safe_handle(handle):
    """Keep only characters safe for an Apify media storage key."""
    return re.sub(r"[^A-Za-z0-9_]", "", handle or "") or "x"


def media_file_key(kind, handle, post_id, index, run_ts):
    """Build a stable media key within the image or video prefix."""
    ext = "mp4" if kind in ("video", "gif") else "jpg"
    prefix = "video" if kind in ("video", "gif") else "image"
    # "/" would be rejected by the key-value store, hence the "_" separator.
    return "%s_%s_%s_%d_p%d.%s" % (prefix, safe_handle(handle), post_id, run_ts, index, ext)


def best_media_asset(item):
    """Resolve the best downloadable asset for a media item, or None."""
    if item.kind == "image":
        url = x2md.upgrade_image_url(item.url)
        return (url, "jpg") if url else None
    download_url = item.video_url or x2md.upgrade_image_url(item.url)
    return (download_url, "mp4") if download_url else None


def plan_media_downloads(doc, download_media, run_ts):
    """List ``{"key", "download_url"}`` uploads the Actor should perform."""
    plan = []
    for post in doc.posts:
        post_id = post.post_id or doc.status_id
        for index, item in enumerate(post.media):
            toggle = KIND_TO_TOGGLE.get(item.kind)
            if not toggle or not download_media.get(toggle):
                continue
            asset = best_media_asset(item)
            if asset is None:
                continue
            download_url, _ext = asset
            plan.append(
                {
                    "key": media_file_key(item.kind, post.author.handle, post_id, index, run_ts),
                    "download_url": download_url,
                }
            )
    return plan


def media_to_ref(item, handle, post_id, index, download_media, run_ts):
    """Map one media asset to its public URL and optional stored file key."""
    kind = item.kind if item.kind in ("image", "video", "gif") else "image"
    asset = best_media_asset(item)
    ref = {
        "type": kind,
        "url": asset[0] if asset else (item.video_url or item.url),
        "fileKey": None,
        "altText": item.alt or "",
    }
    toggle = KIND_TO_TOGGLE[kind]
    if download_media.get(toggle) and asset is not None:
        ref["fileKey"] = media_file_key(kind, handle, post_id, index, run_ts)
    if kind == "video" and item.video_url:
        ref["videoVariants"] = [item.video_url]
    return ref


def post_to_payload(post, doc, position, download_media, run_ts, cli_post=None):
    """Map one x2md ``Post`` onto its dataset-item shape.

    ``cli_post`` is the matching entry from :func:`x2md.document_to_json` — the
    exact structure ``x2md --json`` prints. The poll, quote, and article fields
    are taken straight from it rather than re-derived here, so the Actor cannot
    drift from the CLI on the three richest parts of a post.
    """
    cli_post = cli_post or {}
    stats = {}
    for name in ("likes", "retweets", "replies", "views", "quotes", "bookmarks"):
        value = getattr(post, name)
        if value is not None:
            stats[name] = value
    post_id = post.post_id or doc.status_id
    payload = {
        "id": post_id,
        "url": post.url,
        "text": post.text,
        "author": {"handle": post.author.handle, "name": post.author.name, "avatarUrl": ""},
        "createdAt": post.created_at,
        "lang": post.lang,
        "isNoteTweet": post.is_note_tweet,
        "isSelfReply": post.is_self_reply,
        "stats": stats,
        "kind": doc.kind,
        "threadPosition": position if doc.kind == "thread" else None,
        "threadComplete": doc.thread_complete if doc.kind == "thread" else None,
        "conversationId": doc.status_id if doc.kind == "thread" else None,
        "poll": cli_post.get("poll"),
        "quote": cli_post.get("quote"),
        "article": cli_post.get("article"),
        "media": [
            media_to_ref(m, post.author.handle, post_id, i, download_media, run_ts)
            for i, m in enumerate(post.media)
        ],
    }
    return payload


def document_to_item(doc, errors, download_media, output_format, run_ts):
    """Convert a fetched document to flat and/or nested Actor output."""
    # One pass through x2md's own JSON serializer gives every post its CLI
    # representation; post_to_payload reuses the poll/quote/article branches
    # from it instead of duplicating that logic.
    cli_posts = x2md.document_to_json(doc)["posts"]
    posts = [
        post_to_payload(
            p, doc, i + 1, download_media, run_ts,
            cli_post=cli_posts[i] if i < len(cli_posts) else None,
        )
        for i, p in enumerate(doc.posts)
    ]
    warnings = list(doc.warnings)
    if not doc.thread_complete:
        warnings.insert(0, WARNING_THREAD_INCOMPLETE)
    item = {
        "id": doc.status_id,
        "url": doc.source_url,
        "kind": doc.kind,
        "author": {
            "handle": doc.author.handle,
            "name": doc.author.name,
            "avatarUrl": "",
        },
        "markdown": x2md.render_document(doc),
        "threadComplete": doc.thread_complete if doc.kind == "thread" else None,
        "warnings": warnings,
        "provider": doc.provider,
        "providerErrors": [error_to_dict(e) for e in errors],
    }
    # Nested output only carries a "thread" block for threads; without this
    # branch posts and articles would lose their structured payload entirely.
    if output_format in ("flat", "both") or doc.kind != "thread":
        item["posts"] = posts
    if output_format in ("nested", "both") and doc.kind == "thread":
        item["thread"] = {"posts": posts, "complete": doc.thread_complete}
    return item


def failure_item(url, status_id, errors):
    """Describe a URL for which every provider failed."""
    return {
        "id": status_id,
        "url": url,
        "failedProviders": [error_to_dict(e) for e in errors],
    }


def iter_file_refs(item):
    """Yield media refs carrying a fileKey from a dataset item.

    Nested-only thread items keep their posts under ``thread``; prefer
    ``posts`` whenever it is present so "both" output (where the same dicts
    appear in both places) never yields a ref twice.
    """
    posts = item.get("posts")
    if not posts:
        thread = item.get("thread")
        if isinstance(thread, dict):
            posts = thread.get("posts")
    for post in posts or []:
        for media in post.get("media", []):
            if media.get("fileKey"):
                yield media


def fetch_one(url, cleaned_input, run_ts=None, client=None):
    """Process a single URL/ID into a dataset item (or failure item)."""
    run_ts = run_ts if run_ts is not None else int(time.time() * 1000)
    # Isolation boundary: one bad URL must never abort the whole batch, so
    # an unexpected parser/serializer error is downgraded to a per-item
    # error alongside the invalid-URL and all-providers-failed cases.
    try:
        try:
            target = x2md.parse_target(url)
        except x2md.InputError as exc:
            return {"url": url, "error": str(exc)}
        own_client = client if client is not None else x2md.HttpClient(
            timeout=20, max_retries=2, user_agent="x2md-actor/%s" % x2md.__version__
        )
        providers = x2md.build_providers(cleaned_input["provider"], own_client, {})
        try:
            doc, errors = x2md.fetch_document(target, providers, own_client)
        except x2md.NoProviderAvailable as exc:
            return failure_item(url, target.status_id, exc.errors)
        return document_to_item(
            doc, errors, cleaned_input["downloadMedia"], cleaned_input["outputFormat"], run_ts
        )
    except Exception as exc:
        return {"url": url, "error": "unexpected error: %s" % exc}


def run_batch(cleaned_input, run_ts=None, client=None):
    """Process up to ``maxItems`` URLs; return ``{"items", "kv_keys"}``."""
    run_ts = run_ts if run_ts is not None else int(time.time() * 1000)
    items = []
    kv_keys = []
    for url in cleaned_input["startUrls"][: cleaned_input["maxItems"]]:
        item = fetch_one(url, cleaned_input, run_ts=run_ts, client=client)
        items.append(item)
        kv_keys.extend(ref["fileKey"] for ref in iter_file_refs(item))
    if cleaned_input["downloadMedia"].get("zip") and kv_keys:
        kv_keys.append("zip_run_%d.zip" % run_ts)
    return {"items": items, "kv_keys": kv_keys}
