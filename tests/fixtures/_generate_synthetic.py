#!/usr/bin/env python3
"""Regenerate the synthetic FxTwitter fixtures used by the large-thread tests.

The recorded fixtures next to this script came from real API responses. The two
files written here are synthetic instead, because the cases they cover cannot be
captured from a live account on demand:

``fxtwitter_v2_thread100.json``
    A 100-post self-thread, larger than the Actor's 50-item cap, used to prove
    the cap holds and that a thread that size maps without exhausting the
    128 MB platform memory budget.

``fxtwitter_v2_thread_incomplete.json``
    A single post that replies to its own author with no siblings in the thread
    listing. FxTwitter's v2 API has no ``thread_complete`` field; x2md derives
    incompleteness from exactly this shape (see ``_document_from_fxtwitter_payload``),
    so this is the payload that drives ``thread_complete = False``.

Run from the repository root::

    python3 tests/fixtures/_generate_synthetic.py
"""

import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent

HANDLE = "threadsmith"
AUTHOR_ID = "1700000000000000001"
BASE_ID = 1900000000000000000
BASE_TS = 1782942985

AUTHOR = {
    "screen_name": HANDLE,
    "url": "https://x.com/%s" % HANDLE,
    "id": AUTHOR_ID,
    "followers": 48211,
    "following": 312,
    "likes": 9044,
    "media_count": 188,
    "statuses": 4021,
    "name": "Thread Smith",
    "description": "Synthetic account used by the x2md test suite.",
    "location": "",
    "banner_url": None,
    "avatar_url": "https://pbs.twimg.com/profile_images/%s/avatar.jpg" % AUTHOR_ID,
    "joined": "Tue Mar 03 09:12:00 +0000 2015",
    "website": None,
}

# Long enough that 100 of them are a realistic payload rather than a toy one.
PARAGRAPH = (
    "Step {n} of the build log. We moved the retry budget out of the transport "
    "layer and into the provider loop, which means a slow upstream no longer "
    "burns the whole per-request allowance before the fallback provider is "
    "given a chance to answer. The numbers below are from the staging run, "
    "averaged over twenty consecutive fetches, and they line up with what the "
    "profiler predicted once the connection pool stopped being the bottleneck."
)


def created_at_for(index):
    """Twitter-style date string derived from the same epoch as created_timestamp.

    x2md prefers ``created_at`` over ``created_timestamp``, so both fields must
    describe the same instant or every post would parse to post 0's time.
    """
    return time.strftime("%a %b %d %H:%M:%S +0000 %Y", time.gmtime(BASE_TS + index * 60))


def make_post(index, total, replying_to_self):
    """Create one synthetic FxTwitter post with optional self-reply metadata."""
    post_id = str(BASE_ID + index)
    post = {
        "type": "status",
        "url": "https://x.com/%s/status/%s" % (HANDLE, post_id),
        "id": post_id,
        "text": PARAGRAPH.format(n=index + 1) + "\n\n(%d/%d)" % (index + 1, total),
        "author": dict(AUTHOR),
        "replies": max(0, 40 - index),
        "reposts": max(0, 120 - index * 2),
        "likes": max(0, 900 - index * 7),
        "bookmarks": max(0, 60 - index),
        "quotes": max(0, 12 - index // 4),
        "created_at": created_at_for(index),
        "created_timestamp": BASE_TS + index * 60,
        "possibly_sensitive": False,
        "views": max(0, 300000 - index * 1500),
        "is_note_tweet": False,
        "community_note": None,
        "lang": "en",
        "replying_to": {"screen_name": HANDLE, "post": None} if replying_to_self else None,
        "media": None,
        "source": "Twitter Web App",
        "provider": "twitter",
        "reposted_by": None,
    }
    return post


def write(name, payload):
    """Write a deterministic JSON fixture beside this generator."""
    path = HERE / name
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("wrote %s (%d bytes)" % (path.name, path.stat().st_size))


def main():
    """Regenerate the long and incomplete thread fixtures."""
    # 100-post thread: the focal post opens it, every later post is a self-reply.
    posts = [make_post(i, 100, replying_to_self=i > 0) for i in range(100)]
    write(
        "fxtwitter_v2_thread100.json",
        {"code": 200, "message": "OK", "status": posts[0], "thread": posts, "author": dict(AUTHOR)},
    )

    # Incomplete thread: a self-reply whose siblings the listing did not return.
    orphan = make_post(41, 100, replying_to_self=True)
    write(
        "fxtwitter_v2_thread_incomplete.json",
        {"code": 200, "message": "OK", "status": orphan, "thread": [orphan], "author": dict(AUTHOR)},
    )


if __name__ == "__main__":
    main()
