"""PROTOTYPE — throwaway sample of one x2md Apify Actor run. Not production code.

Answers ticket #7: "what does one Actor run look like end to end?"

Runs fully offline by replaying recorded fixtures through the real x2md.py
pipeline (parse_target -> fetch_document -> render_document), then maps the
result onto the input/output contract locked in tickets #5/#6 (dataset items,
Markdown, KV-store media file keys).

Usage:
    python3 prototype/actor_sample_run.py

Reads:  tests/fixtures/*.json
Writes: prototype/sample-run/   (INPUT.json, dataset.json, *.md, kv-store.txt)
"""

import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))

import _support  # noqa: E402

x2md = _support.x2md

OUTDIR = HERE / "sample-run"

# (label, status_id, thread-route fixture, status-route fixture)
CASES = [
    ("single-post", "20", None, "fxtwitter_v2_status_simple.json"),
    ("thread-5", "2072439205213421694", "fxtwitter_v2_thread5.json", "fxtwitter_v2_thread5.json"),
    ("video-post", "2095249317875622255", "fxtwitter_v2_video.json", "fxtwitter_v2_video.json"),
]

ACTOR_INPUT = {
    "startUrls": [
        "https://x.com/jack/status/20",
        "https://x.com/XCreators/status/2072439205213421694",
        "https://x.com/imagine/status/2095249317875622255",
    ],
    "maxItems": 10,
    "provider": "auto",
    "downloadMedia": {"images": True, "videos": True, "gifs": True, "zip": True},
    "outputFormat": "both",
}

RUN_TS = 1758230400000  # fixed, so KV keys are stable across prototype runs


def kv_key(handle, post_id, index, ext):
    safe = "".join(c for c in (handle or "x") if c.isalnum() or c == "_") or "x"
    return "%s_%s_%d_p%d.%s" % (safe, post_id, RUN_TS, index, ext)


def media_to_actor_ref(media, handle, post_id, index, download_media):
    kind = media.kind if media.kind in ("image", "video", "gif") else "image"
    ext = "mp4" if kind in ("video", "gif") else "jpg"
    ref = {
        "type": kind,
        "url": media.video_url or media.url,
        "fileKey": None,
        "altText": media.alt or "",
    }
    if download_media.get("images") and kind == "image":
        ref["fileKey"] = "image/" + kv_key(handle, post_id, index, ext)
    elif download_media.get("videos") and kind == "video":
        ref["fileKey"] = "video/" + kv_key(handle, post_id, index, ext)
        ref["videoVariants"] = [media.video_url] if media.video_url else []
    elif download_media.get("gifs") and kind == "gif":
        ref["fileKey"] = "video/" + kv_key(handle, post_id, index, ext)
    return ref


def document_to_dataset_item(doc, errors, download_media, output_format):
    primary = doc.primary
    posts_payload = []
    for i, post in enumerate(doc.posts):
        media_refs = [
            media_to_actor_ref(m, post.author.handle, post.post_id, j, download_media)
            for j, m in enumerate(post.media)
        ]
        posts_payload.append(
            {
                "id": post.post_id,
                "url": post.url,
                "text": post.text,
                "author": {
                    "handle": post.author.handle,
                    "name": post.author.name,
                    "avatarUrl": "",
                },
                "createdAt": post.created_at,
                "stats": {
                    k: v
                    for k, v in (
                        ("likes", post.likes),
                        ("retweets", post.retweets),
                        ("replies", post.replies),
                        ("quotes", post.quotes),
                        ("bookmarks", post.bookmarks),
                    )
                    if v is not None
                },
                "kind": doc.kind,
                "threadPosition": i + 1 if doc.kind == "thread" else None,
                "threadComplete": doc.thread_complete if doc.kind == "thread" else None,
                "conversationId": doc.status_id if doc.kind == "thread" else None,
                "media": media_refs,
            }
        )
    markdown = x2md.render_document(doc)
    item = {
        "id": doc.status_id,
        "url": doc.source_url,
        "kind": doc.kind,
        "author": {
            "handle": doc.author.handle,
            "name": doc.author.name,
            "avatarUrl": "",
        },
        "markdown": markdown,
        "warnings": list(doc.warnings),
        "provider": doc.provider,
        "providerErrors": [
            {"provider": e.provider, "message": e.message, "url": e.url, "status": e.status}
            for e in errors
        ],
    }
    if output_format in ("flat", "both"):
        item["posts"] = posts_payload
    if output_format in ("nested", "both") and doc.kind == "thread":
        item["thread"] = {"posts": posts_payload, "complete": doc.thread_complete}
    return item


def main():
    # Wipe the output dir so stale files from earlier runs cannot linger.
    # (Exact-match routes below must use FULL URLs: FakeHttp resolves the
    # first substring hit, and "…/thread/20" is a prefix of "…/thread/207…".)
    if OUTDIR.exists():
        for child in OUTDIR.iterdir():
            child.unlink()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "INPUT.json").write_text(json.dumps(ACTOR_INPUT, indent=2), encoding="utf-8")

    routes = {}
    for _label, status_id, thread_fixture, status_fixture in CASES:
        # FxTwitterProvider.fetch always tries /2/thread/{id} first and falls
        # back to /2/status/{id}; register both so the single-post fallback
        # resolves to the same fixture.
        routes["https://api.fxtwitter.com/2/thread/%s" % status_id] = (
            thread_fixture or status_fixture
        )
        routes["https://api.fxtwitter.com/2/status/%s" % status_id] = status_fixture

    fake = _support.install_fake_http(routes)
    dataset = []
    kv_files = []
    try:
        for label, status_id, _t, _s in CASES:
            url = "https://x.com/i/status/%s" % status_id
            target = x2md.parse_target(url)
            client = x2md.HttpClient(timeout=20, max_retries=2)
            providers = x2md.build_providers("auto", client, {})
            try:
                doc, errors = x2md.fetch_document(target, providers, client)
            except x2md.NoProviderAvailable as exc:
                dataset.append(
                    {
                        "id": status_id,
                        "url": url,
                        "failedProviders": [
                            {
                                "provider": e.provider,
                                "message": e.message,
                                "url": e.url,
                                "status": e.status,
                            }
                            for e in exc.errors
                        ],
                    }
                )
                continue
            item = document_to_dataset_item(
                doc, errors, ACTOR_INPUT["downloadMedia"], ACTOR_INPUT["outputFormat"]
            )
            dataset.append(item)
            # Simulate the KV-store uploads the Actor would perform.
            for post in item.get("posts", []):
                for m in post.get("media", []):
                    if m.get("fileKey"):
                        kv_files.append(m["fileKey"])
            stem = "%s_%s" % (item["author"]["handle"] or "x", item["id"])
            (OUTDIR / ("%s.md" % stem)).write_text(item["markdown"], encoding="utf-8")
    finally:
        _support.restore_http()

    (OUTDIR / "dataset.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    if ACTOR_INPUT["downloadMedia"]["zip"]:
        kv_files.append("zip/run_%d.zip" % RUN_TS)
    (OUTDIR / "kv-store.txt").write_text("\n".join(sorted(set(kv_files))) + "\n", encoding="utf-8")

    print("PROTOTYPE sample run complete (offline, fixture-backed)")
    print("  cases        : %d" % len(CASES))
    print("  dataset items: %d" % len(dataset))
    print("  kv files     : %d" % len(set(kv_files)))
    print("  output dir   : %s" % OUTDIR)
    print("  http calls   : %d (all stubbed)" % len(fake.calls))
    for call in fake.calls:
        print("    %s %s -> HTTP %s" % (call["provider"], call["url"], call["status"]))


if __name__ == "__main__":
    main()
