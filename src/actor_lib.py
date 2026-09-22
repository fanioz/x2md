"""Mapping layer between the Apify Actor runtime and the x2md.py core.

Stdlib only: the apify SDK (`async with Actor`, `push_data`, `set_value`,
proxy, logging) lives in ``main.py``. Everything here is pure and unit
tested offline via ``tests/test_actor.py``.

Decisions (from wayfinder tickets #4/#5/#6):
- input: ``startUrls`` (URLs or bare IDs, incl. requestListSources objects),
  ``maxItems`` (default 10, hard cap 50), ``provider`` (auto default with
  optional override), ``downloadMedia`` (granular images/videos/gifs/zip
  toggles, all on by default), ``outputFormat`` (flat/nested/both).
- output: one dataset item per URL — flat ``posts`` plus optional nested
  ``thread`` — with Markdown body, media refs incl. ``fileKey``, warnings,
  and ``provider`` + ``providerErrors``. Total failure yields a
  ``failedProviders`` chain instead.
- media keys: ``<prefix>/<handle>_<postid>_<timestamp>_p<index>.<ext>``.
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
VALID_PROVIDERS = ("auto", "fxtwitter", "vxtwitter", "syndication", "graphql")
VALID_OUTPUT_FORMATS = ("flat", "nested", "both")
MEDIA_TOGGLES = ("images", "videos", "gifs", "zip")
KIND_TO_TOGGLE = {"image": "images", "video": "videos", "gif": "gifs"}


class ActorInputError(ValueError):
    """Raised when the Actor input fails validation."""


def error_to_dict(exc):
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
    max_items = min(max_items, MAX_ITEMS_HARD_CAP)

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
    return re.sub(r"[^A-Za-z0-9_]", "", handle or "") or "x"


def media_file_key(kind, handle, post_id, index, run_ts):
    ext = "mp4" if kind in ("video", "gif") else "jpg"
    prefix = "video" if kind in ("video", "gif") else "image"
    return "%s/%s_%s_%d_p%d.%s" % (prefix, safe_handle(handle), post_id, run_ts, index, ext)


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


def post_to_payload(post, doc, position, download_media, run_ts):
    stats = {}
    for name in ("likes", "retweets", "replies", "quotes", "bookmarks"):
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
        "stats": stats,
        "kind": doc.kind,
        "threadPosition": position if doc.kind == "thread" else None,
        "threadComplete": doc.thread_complete if doc.kind == "thread" else None,
        "conversationId": doc.status_id if doc.kind == "thread" else None,
        "media": [
            media_to_ref(m, post.author.handle, post_id, i, download_media, run_ts)
            for i, m in enumerate(post.media)
        ],
    }
    return payload


def document_to_item(doc, errors, download_media, output_format, run_ts):
    posts = [
        post_to_payload(p, doc, i + 1, download_media, run_ts)
        for i, p in enumerate(doc.posts)
    ]
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
        "warnings": list(doc.warnings),
        "provider": doc.provider,
        "providerErrors": [error_to_dict(e) for e in errors],
    }
    if output_format in ("flat", "both"):
        item["posts"] = posts
    if output_format in ("nested", "both") and doc.kind == "thread":
        item["thread"] = {"posts": posts, "complete": doc.thread_complete}
    return item


def failure_item(url, status_id, errors):
    return {
        "id": status_id,
        "url": url,
        "failedProviders": [error_to_dict(e) for e in errors],
    }


def iter_file_refs(item):
    """Yield media refs carrying a fileKey from a dataset item."""
    for post in item.get("posts", []):
        for media in post.get("media", []):
            if media.get("fileKey"):
                yield media


def fetch_one(url, cleaned_input, run_ts=None, client=None):
    """Process a single URL/ID into a dataset item (or failure item)."""
    run_ts = run_ts if run_ts is not None else int(time.time() * 1000)
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
        kv_keys.append("zip/run_%d.zip" % run_ts)
    return {"items": items, "kv_keys": kv_keys}
