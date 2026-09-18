#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x2md - convert X (Twitter) posts, self-threads and long-form Articles to Markdown.

Standard library only. Python 3.9+.

Retrieval strategies are pluggable "providers". See ``--provider`` and README.md.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import datetime
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"

PROG = "x2md"

DEFAULT_UA = "x2md/%s" % __version__
# Deliberately NOT a browser User-Agent. Measured on 2026-09-18: sending a Chrome
# UA to api.vxtwitter.com yields HTTP 403, while any honest UA (curl's default,
# "x2md/1.0", "python-urllib/3.9") yields HTTP 200. It also avoids impersonation.

# Public web bearer token, the same constant shipped in X's own web client.
# This is not a secret and not a user credential; it identifies the client app.
PUBLIC_WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Query ids rotate whenever X ships a new web build. They are supplied by the
# operator, not hardcoded to a stale value, so the failure mode is a clean
# "unknown query id" rather than a silently wrong document.
GRAPHQL_QUERY_ID_ENV = "X2MD_GRAPHQL_QUERY_ID"

ACCEPTED_HOSTS = {
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}

_ID_RE = re.compile(r"^\d{1,25}$")
_LEADING_DIGITS_RE = re.compile(r"^(\d{1,25})")
_HTML_TAG_RE = re.compile(r"<(?=[A-Za-z/!?])")
_IMG_NAME_RE = re.compile(r"([?&])name=[^&]*")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class X2mdError(Exception):
    """Base class for expected, user-facing failures."""


class InputError(X2mdError):
    """The URL / id argument could not be understood."""


class ProviderError(X2mdError):
    """A single retrieval strategy failed.

    Carries enough context that ``--debug`` and the fallback chain can report
    exactly which provider failed, at which endpoint, with which HTTP status.
    """

    def __init__(
        self,
        provider: str,
        message: str,
        url: Optional[str] = None,
        status: Optional[int] = None,
    ) -> None:
        self.provider = provider
        self.message = message
        self.url = url
        self.status = status
        super().__init__(self.describe())

    def describe(self) -> str:
        bits = ["provider '%s'" % self.provider]
        if self.status is not None:
            bits.append("HTTP %s" % self.status)
        if self.url:
            bits.append(self.url)
        return "%s: %s" % (", ".join(bits), self.message)


class NoProviderAvailable(X2mdError):
    """Every candidate strategy failed."""

    def __init__(self, errors: Sequence[ProviderError]) -> None:
        self.errors = list(errors)
        lines = ["all retrieval strategies failed:"]
        for err in self.errors:
            lines.append("  - %s" % err.describe())
        super().__init__("\n".join(lines))


# --------------------------------------------------------------------------- #
# Input parsing
# --------------------------------------------------------------------------- #


@dataclass
class Target:
    """A parsed user argument."""

    status_id: str
    handle: Optional[str] = None
    source_url: str = ""
    from_url: bool = False

    @property
    def canonical_url(self) -> str:
        if self.handle:
            return "https://x.com/%s/status/%s" % (self.handle, self.status_id)
        return "https://x.com/i/status/%s" % self.status_id

    @property
    def display_url(self) -> str:
        return self.source_url or self.canonical_url


def _normalise_host(netloc: str) -> str:
    host = netloc.rsplit("@", 1)[-1]
    if host.count(":") == 1:  # strip :port, keep [v6] intact
        host = host.split(":", 1)[0]
    return host.lower().strip(".")


def parse_target(raw: str) -> Target:
    """Parse a URL or a bare status id into a :class:`Target`.

    Accepts ``x.com``/``twitter.com`` and their ``www.``/``mobile.`` variants,
    with or without query strings or fragments, in any of these shapes::

        https://x.com/<handle>/status/<id>
        https://mobile.x.com/<handle>/status/<id>?s=20
        https://twitter.com/i/web/status/<id>
        https://x.com/<handle>/status/<id>/photo/1
        https://x.com/<handle>/statuses/<id>
        https://x.com/i/article/<id>
        <id>
    """
    if raw is None:
        raise InputError("no URL or status id given")
    text = raw.strip().strip("\u200b")
    if not text:
        raise InputError("empty URL or status id")

    if _ID_RE.match(text):
        return Target(status_id=text, source_url="https://x.com/i/status/%s" % text)

    candidate = text if "://" in text else "https://" + text
    try:
        parsed = urllib.parse.urlsplit(candidate)
    except ValueError as exc:
        raise InputError("could not parse %r as a URL: %s" % (raw, exc))

    host = _normalise_host(parsed.netloc)
    if not host:
        raise InputError("could not find a host in %r" % raw)
    if host not in ACCEPTED_HOSTS:
        raise InputError(
            "unsupported host %r; expected one of: %s"
            % (host, ", ".join(sorted(ACCEPTED_HOSTS)))
        )

    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        raise InputError("URL %r has no path; expected .../status/<id>" % raw)

    status_id: Optional[str] = None
    handle: Optional[str] = None

    for marker in ("status", "statuses", "article"):
        if marker not in segments:
            continue
        idx = len(segments) - 1 - segments[::-1].index(marker)
        if idx + 1 >= len(segments):
            raise InputError("URL %r ends with '%s' but has no id" % (raw, marker))
        match = _LEADING_DIGITS_RE.match(segments[idx + 1])
        if not match:
            raise InputError(
                "segment after '%s' in %r is not a numeric id: %r"
                % (marker, raw, segments[idx + 1])
            )
        status_id = match.group(1)
        if idx >= 1:
            maybe = segments[idx - 1]
            if maybe.lower() not in ("i", "web", "status", "statuses", "article"):
                handle = maybe
        break

    if status_id is None:
        for seg in reversed(segments):
            if _ID_RE.match(seg):
                status_id = seg
                break

    if status_id is None:
        raise InputError(
            "could not find a post id in %r; expected a URL like "
            "https://x.com/<handle>/status/<id>" % raw
        )

    source = "https://x.com/"
    if handle:
        source += "%s/status/%s" % (handle, status_id)
    else:
        source += "i/status/%s" % status_id
    return Target(
        status_id=status_id, handle=handle, source_url=source, from_url=True
    )


# --------------------------------------------------------------------------- #
# Escaping helpers
# --------------------------------------------------------------------------- #


def escape_text(value: str) -> str:
    """Escape text so it cannot inject raw HTML when embedded in Markdown.

    Markdown renderers decode these entities, so the visible text is unchanged.
    """
    if not value:
        return ""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_markdown_link_text(value: str) -> str:
    """Escape text used as the label of an inline link."""
    out = escape_text(value)
    return out.replace("[", "\\[").replace("]", "\\]")


def escape_markdown_url(value: str) -> str:
    """Make a URL safe to place inside ``(...)`` of a Markdown link."""
    return (
        value.replace("\\", "%5C")
        .replace("(", "%28")
        .replace(")", "%29")
        .replace(" ", "%20")
        .replace("<", "%3C")
        .replace(">", "%3E")
    )


def neutralise_raw_html(value: str) -> str:
    """Neutralise HTML tags while leaving Markdown syntax intact.

    Used for author-supplied Markdown (article ``MARKDOWN`` entities) where the
    markup is wanted but a ``<script>`` tag is not.
    """
    if not value:
        return ""
    return _HTML_TAG_RE.sub("&lt;", value)


def yaml_scalar(value: Any) -> str:
    """Render a value as a YAML double-quoted scalar.

    Double-quoted YAML scalars are a superset of JSON strings, so ``json.dumps``
    gives us correct escaping for quotes, backslashes, colons, newlines and
    control characters. U+2028/U+2029/U+0085 are escaped explicitly because some
    YAML readers treat them as line breaks.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    encoded = json.dumps(text, ensure_ascii=False)
    # json.dumps leaves U+2028/U+2029/U+0085 literal when ensure_ascii=False, and
    # some YAML readers treat them as line breaks inside a flow scalar. The escape
    # is applied *after* encoding so the backslash is not itself escaped, which
    # keeps the round trip exact.
    for raw, escaped in (
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
        ("\u0085", "\\u0085"),
    ):
        encoded = encoded.replace(raw, escaped)
    return encoded


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Author:
    name: str = ""
    handle: str = ""
    url: str = ""
    author_id: str = ""

    @property
    def byline(self) -> str:
        if self.name and self.handle:
            return "%s (@%s)" % (self.name, self.handle)
        if self.handle:
            return "@%s" % self.handle
        return self.name or "unknown author"


@dataclass
class Media:
    kind: str = "image"  # image | video | gif
    url: str = ""  # highest-resolution image / video thumbnail
    alt: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    video_url: Optional[str] = None
    duration: Optional[float] = None


@dataclass
class PollChoice:
    label: str = ""
    count: Optional[int] = None
    percentage: Optional[float] = None


@dataclass
class Poll:
    choices: List[PollChoice] = field(default_factory=list)
    total_votes: Optional[int] = None
    ends_at: Optional[str] = None


@dataclass
class ArticleBlock:
    type: str = "unstyled"
    text: str = ""
    entity_ranges: List[Dict[str, Any]] = field(default_factory=list)
    inline_style_ranges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Article:
    article_id: str = ""
    title: str = ""
    preview_text: str = ""
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    cover: Optional[Media] = None
    blocks: List[ArticleBlock] = field(default_factory=list)
    entity_map: List[Dict[str, Any]] = field(default_factory=list)
    media_entities: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Post:
    post_id: str = ""
    url: str = ""
    text: str = ""
    created_at: Optional[str] = None
    author: Author = field(default_factory=Author)
    lang: str = ""
    facets: List[Dict[str, Any]] = field(default_factory=list)
    media: List[Media] = field(default_factory=list)
    poll: Optional[Poll] = None
    quote: Optional["Post"] = None
    article: Optional[Article] = None
    is_note_tweet: bool = False
    is_self_reply: bool = False
    likes: Optional[int] = None
    retweets: Optional[int] = None
    replies: Optional[int] = None
    views: Optional[int] = None
    quotes: Optional[int] = None
    bookmarks: Optional[int] = None


@dataclass
class Document:
    kind: str = "post"  # post | thread | article
    source_url: str = ""
    status_id: str = ""
    author: Author = field(default_factory=Author)
    posts: List[Post] = field(default_factory=list)
    provider: str = ""
    thread_complete: bool = True
    warnings: List[str] = field(default_factory=list)

    @property
    def primary(self) -> Post:
        if not self.posts:
            raise X2mdError("document has no posts")
        return self.posts[0]


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

_TWITTER_DATE_FORMATS = ("%a %b %d %H:%M:%S %z %Y",)


def to_iso8601(value: Any) -> Optional[str]:
    """Best-effort conversion of a provider date field to ISO 8601 UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(
                float(value), tz=datetime.timezone.utc
            )
        except (OverflowError, OSError, ValueError):
            return None
        return dt.replace(microsecond=0).isoformat()
    text = str(value).strip()
    for fmt in _TWITTER_DATE_FORMATS:
        try:
            dt = datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return dt.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()
    iso = text
    if iso.endswith("Z") or iso.endswith("z"):
        iso = iso[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = value.strip().replace(",", "")
        if digits.isdigit():
            return int(digits)
    return None


# --------------------------------------------------------------------------- #
# Image URL upgrading
# --------------------------------------------------------------------------- #


def upgrade_image_url(url: str) -> str:
    """Return the highest-resolution form of a ``pbs.twimg.com`` image URL.

    ``?name=small|medium|large`` is rewritten to ``?name=orig``; bare media URLs
    get ``?name=orig`` appended.
    """
    if not url:
        return url
    if "pbs.twimg.com" not in url:
        return url
    if _IMG_NAME_RE.search(url):
        return _IMG_NAME_RE.sub(lambda m: m.group(1) + "name=orig", url)
    if "/media/" in url or "profile_images" in url:
        joiner = "&" if "?" in url else "?"
        return url + joiner + "name=orig"
    return url


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


@dataclass
class HttpResponse:
    status: int
    url: str
    body: bytes
    headers: Dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8", "replace"))

    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


class HttpClient:
    """Small sequential HTTP client with 429-aware retries.

    Deliberately serial: at most a handful of requests per URL, no parallelism.
    """

    def __init__(
        self,
        debug: bool = False,
        timeout: float = 20.0,
        max_retries: int = 2,
        backoff: float = 1.5,
        max_backoff: float = 15.0,
        user_agent: str = DEFAULT_UA,
        stream=None,
    ) -> None:
        self.debug = debug
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.max_backoff = max_backoff
        self.user_agent = user_agent
        self.stream = stream if stream is not None else sys.stderr
        self.request_count = 0

    def _log(self, message: str) -> None:
        if self.debug:
            print("[debug] %s" % message, file=self.stream, flush=True)

    def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        provider: str = "-",
    ) -> HttpResponse:
        send_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            send_headers.update(headers)

        attempt = 0
        while True:
            attempt += 1
            self.request_count += 1
            request = urllib.request.Request(
                url, data=body, headers=send_headers, method=method
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    payload = resp.read()
                    status = resp.getcode()
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                self._log(
                    "%s %s %s -> HTTP %s, %d bytes"
                    % (provider, method, url, status, len(payload))
                )
                if status in (429, 500, 502, 503, 504) and attempt <= self.max_retries:
                    delay = self._retry_delay(resp_headers, attempt)
                    self._log(
                        "%s retrying after HTTP %s in %.1fs (attempt %d/%d)"
                        % (provider, status, delay, attempt, self.max_retries)
                    )
                    time.sleep(delay)
                    continue
                return HttpResponse(
                    status=status, url=url, body=payload, headers=resp_headers
                )
            except urllib.error.HTTPError as exc:
                payload = b""
                try:
                    payload = exc.read()
                except Exception:  # pragma: no cover - defensive
                    payload = b""
                status = exc.code
                resp_headers = {
                    k.lower(): v for k, v in (exc.headers or {}).items()
                }
                self._log(
                    "%s %s %s -> HTTP %s, %d bytes"
                    % (provider, method, url, status, len(payload))
                )
                if status in (429, 500, 502, 503, 504) and attempt <= self.max_retries:
                    delay = self._retry_delay(resp_headers, attempt)
                    self._log(
                        "%s retrying after HTTP %s in %.1fs (attempt %d/%d)"
                        % (provider, status, delay, attempt, self.max_retries)
                    )
                    time.sleep(delay)
                    continue
                return HttpResponse(
                    status=status, url=url, body=payload, headers=resp_headers
                )
            except urllib.error.URLError as exc:
                self._log("%s %s %s -> network error: %s" % (provider, method, url, exc))
                if attempt <= self.max_retries:
                    delay = min(self.backoff * attempt, self.max_backoff)
                    self._log(
                        "%s retrying after network error in %.1fs (attempt %d/%d)"
                        % (provider, delay, attempt, self.max_retries)
                    )
                    time.sleep(delay)
                    continue
                raise ProviderError(
                    provider, "network error: %s" % exc.reason, url
                )
            except TimeoutError as exc:  # pragma: no cover - defensive
                self._log("%s %s %s -> timeout" % (provider, method, url))
                if attempt <= self.max_retries:
                    time.sleep(min(self.backoff * attempt, self.max_backoff))
                    continue
                raise ProviderError(provider, "request timed out: %s" % exc, url)

    def _retry_delay(self, headers: Dict[str, str], attempt: int) -> float:
        raw = headers.get("retry-after")
        if raw:
            try:
                return min(float(raw), self.max_backoff)
            except ValueError:
                pass
        return min(self.backoff * attempt, self.max_backoff)


def _require_json(resp: HttpResponse, provider: str) -> Any:
    """Parse a JSON body, or raise a descriptive error for HTML/bot walls."""
    head = resp.body[:200].lstrip()
    if head.startswith(b"<"):
        snippet = " ".join(resp.text()[:120].split())
        hint = ""
        lowered = resp.text()[:2000].lower()
        if "just a moment" in lowered or "cloudflare" in lowered or "cf_chl" in lowered:
            hint = " (looks like a bot-protection/interstitial page)"
        raise ProviderError(
            provider,
            "expected JSON but received HTML%s; body starts: %r" % (hint, snippet),
            resp.url,
            resp.status,
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(
            provider,
            "response was not valid JSON: %s; body starts: %r"
            % (exc, resp.text()[:120]),
            resp.url,
            resp.status,
        )


# --------------------------------------------------------------------------- #
# Facet-aware text rendering
# --------------------------------------------------------------------------- #


def _utf16_boundaries(text: str) -> List[int]:
    """UTF-16 code-unit offset of every Python string index in ``text``."""
    offsets = [0]
    total = 0
    for ch in text:
        total += 2 if ord(ch) > 0xFFFF else 1
        offsets.append(total)
    return offsets


# NOTE ON FACET OFFSETS
# FxTwitter's OpenAPI document describes facet `indices` as "UTF-16 indices", but
# live `raw_text.facets` payloads index the raw text by *codepoint*: verified against
# a post containing the astral character U+1D54F, where codepoint slicing selects the
# exact expected substring and UTF-16 slicing is off by one. `facet_indices_are_utf16`
# is therefore False by default and the observed behaviour is followed. Media facets
# are additionally unreliable -- their ranges can exceed the text length entirely --
# so every range is bounds-checked and out-of-range facets are dropped, not trusted.
FACET_INDICES_ARE_UTF16 = False


def _facet_slice(text: str, start: int, end: int) -> Optional[Tuple[int, int]]:
    """Translate a facet ``[start, end)`` range into Python string indices."""
    if start < 0 or end <= start:
        return None
    if FACET_INDICES_ARE_UTF16:
        boundaries = _utf16_boundaries(text)
        if end > boundaries[-1]:
            return None
        py_start = bisect.bisect_left(boundaries, start)
        py_end = bisect.bisect_left(boundaries, end)
    else:
        if end > len(text):
            return None
        py_start, py_end = start, end
    if py_end > len(text) or py_start >= py_end:
        return None
    return py_start, py_end


def splice_spans(
    text: str, spans: Sequence[Tuple[int, int, str]]
) -> str:
    """Rebuild ``text`` applying ``(start, end, replacement)`` spans in one pass.

    Plain segments are HTML-escaped; replacement strings are emitted verbatim so
    caller-generated Markdown is not mangled. All offsets are in Python string
    indices and must refer to the *original* text. Overlapping spans are dropped.
    """
    accepted: List[Tuple[int, int, str]] = []
    for span in sorted(spans, key=lambda s: (s[0], s[1])):
        if span[0] >= span[1] or span[0] < 0 or span[1] > len(text):
            continue
        if accepted and span[0] < accepted[-1][1]:
            continue  # overlapping, skip
        accepted.append(span)

    out: List[str] = []
    pos = 0
    for start, end, replacement in accepted:
        out.append(escape_text(text[pos:start]))
        out.append(replacement)
        pos = end
    out.append(escape_text(text[pos:]))
    return "".join(out)


def render_text_with_facets(text: str, facets: Sequence[Dict[str, Any]]) -> str:
    """Render post text, turning URL facets into inline Markdown links.

    * URL facets become ``[display](target)`` (or ``<target>`` when the visible
      text is already the URL).
    * Media facets are dropped: the media itself is rendered in a Media section,
      so keeping the ``pic.x.com/...`` placeholder would duplicate it.
    * Hashtag / mention / cashtag facets are deliberately left as plain readable
      text rather than being rewritten into links.
    * Every literal segment is HTML-escaped so post text cannot inject markup.
    """
    if not text:
        return ""
    spans: List[Tuple[int, int, str]] = []

    for facet in facets or []:
        if not isinstance(facet, dict):
            continue
        kind = facet.get("type")
        indices = facet.get("indices")
        if not isinstance(indices, (list, tuple)) or len(indices) != 2:
            continue
        try:
            u_start, u_end = int(indices[0]), int(indices[1])
        except (TypeError, ValueError):
            continue
        bounds = _facet_slice(text, u_start, u_end)
        if bounds is None:
            continue
        start, end = bounds

        if kind == "media":
            spans.append((start, end, ""))
            continue

        if kind == "url":
            target = facet.get("replacement") or facet.get("original") or ""
            if not target:
                continue
            # Prefer the human-readable display form (e.g. "x.com/i/live-studio")
            # over the raw t.co alias that appears in raw_text.
            visible = str(facet.get("display") or "") or text[start:end]
            if visible.strip() == str(target).strip():
                spans.append(
                    (start, end, "<%s>" % escape_markdown_url(str(target)))
                )
            else:
                spans.append(
                    (
                        start,
                        end,
                        "[%s](%s)"
                        % (
                            escape_markdown_link_text(visible),
                            escape_markdown_url(str(target)),
                        ),
                    )
                )

    return splice_spans(text, spans)


# --------------------------------------------------------------------------- #
# Block rendering primitives
# --------------------------------------------------------------------------- #


def hard_breaks(text: str) -> str:
    """Preserve single line breaks through Markdown rendering.

    CommonMark collapses a single newline inside a paragraph, so a trailing
    backslash is added to lines that are followed by a non-blank line. Blank lines
    are left untouched: they already terminate the paragraph, and marking them would
    emit a stray backslash.
    """
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    out: List[str] = []
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        followed_by_text = (not is_last) and bool(lines[index + 1].strip())
        if line.strip() and followed_by_text and not line.endswith("\\"):
            out.append(line + "\\")
        else:
            out.append(line)
    return "\n".join(out)


def single_line(value: str) -> str:
    """Collapse whitespace so a value is safe to embed in a one-line context.

    Used for headings, bylines and attributions, where an embedded newline from
    post or author text would otherwise break the document structure.
    """
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def blockquote(text: str, depth: int = 1) -> List[str]:
    prefix = "> " * depth
    lines = text.split("\n")
    return [prefix + line if line else prefix.rstrip() for line in lines]


def render_media_list(media: Sequence[Media], heading: Optional[str] = "Media") -> List[str]:
    """Render media as Markdown links to the best available image/thumbnail."""
    if not media:
        return []
    lines: List[str] = []
    if heading:
        lines.append("**%s**" % heading)
        lines.append("")
    for item in media:
        label = single_line(item.alt)
        if item.kind == "image":
            alt = escape_markdown_link_text(label or "image")
            lines.append("- ![%s](%s)" % (alt, escape_markdown_url(item.url)))
            continue
        kind_label = "Video" if item.kind == "video" else "GIF"
        alt = escape_markdown_link_text(label or ("%s thumbnail" % kind_label))
        lines.append("- [%s](%s)" % (alt, escape_markdown_url(item.url)))
        detail_bits: List[str] = []
        if item.video_url:
            detail_bits.append("[%s file](%s)" % (kind_label, escape_markdown_url(item.video_url)))
        dims = []
        if item.width and item.height:
            dims.append("%dx%d" % (item.width, item.height))
        if item.duration:
            dims.append("%.1fs" % item.duration)
        if dims:
            detail_bits.append(", ".join(dims))
        if detail_bits:
            lines.append("  - %s" % " — ".join(detail_bits))
    return lines


def render_poll(poll: Poll) -> List[str]:
    """Render a poll as a list of options with percentages."""
    if not poll or not poll.choices:
        return []
    meta: List[str] = []
    if poll.total_votes is not None:
        meta.append("%s votes" % "{:,}".format(poll.total_votes))
    if poll.ends_at:
        meta.append("ends %s" % poll.ends_at)
    header = "**Poll**"
    if meta:
        header += " (%s)" % "; ".join(meta)
    lines = [header, ""]
    for choice in poll.choices:
        parts: List[str] = []
        if choice.percentage is not None:
            parts.append("%.1f%%" % choice.percentage)
        if choice.count is not None:
            parts.append("{:,} votes".format(choice.count))
        suffix = " — %s" % ", ".join(parts) if parts else ""
        lines.append("- %s%s" % (single_line(escape_text(choice.label)), suffix))
    return lines


def render_quote(post: Optional[Post], depth: int = 1) -> List[str]:
    """Render a quoted post as a nested blockquote with its own attribution."""
    if post is None:
        return []
    inner: List[str] = []
    attr = "**%s**" % single_line(escape_text(post.author.byline))
    if post.created_at:
        attr += " — %s" % post.created_at
    inner.append(attr)
    inner.append("")
    if post.text:
        # post.text is already rendered Markdown (escaped, links resolved), so it
        # is emitted as-is rather than escaped a second time.
        inner.extend(hard_breaks(post.text).split("\n"))
    if post.media:
        inner.append("")
        inner.extend(render_media_list(post.media, heading=None))
    if post.poll:
        inner.append("")
        inner.extend(render_poll(post.poll))
    if post.quote:
        inner.append("")
        inner.extend(render_quote(post.quote, depth + 1))
    if post.url:
        inner.append("")
        inner.append("<%s>" % escape_markdown_url(post.url))
    rendered = blockquote("\n".join(inner), depth=depth)
    return rendered


# --------------------------------------------------------------------------- #
# Article rendering (Draft.js -> Markdown)
# --------------------------------------------------------------------------- #

_ARTICLE_HEADING_LEVELS = {
    "header-one": "##",
    "header-two": "###",
    "header-three": "####",
    "header-four": "#####",
    "header-five": "######",
    "header-six": "######",
}


def _media_from_article_entity(
    entity: Dict[str, Any], media_entities: Sequence[Dict[str, Any]]
) -> List[Media]:
    """Resolve a ``MEDIA`` entity to concrete media via ``media_entities``."""
    by_id = {}
    for entry in media_entities or []:
        if isinstance(entry, dict) and entry.get("media_id"):
            by_id[str(entry["media_id"])] = entry

    out: List[Media] = []
    data = ((entity or {}).get("value") or {}).get("data") or {}
    for item in data.get("mediaItems") or []:
        media_id = str(item.get("mediaId") or "")
        entry = by_id.get(media_id)
        if not entry:
            continue
        info = entry.get("media_info") or {}
        typename = info.get("__typename")
        if typename == "ApiImage":
            out.append(
                Media(
                    kind="image",
                    url=upgrade_image_url(info.get("original_img_url") or ""),
                    alt=info.get("ext_alt_text") or "",
                    width=_coerce_int(info.get("original_img_width")),
                    height=_coerce_int(info.get("original_img_height")),
                )
            )
        else:
            thumb = info.get("media_url_https") or info.get("media_url") or ""
            original = info.get("original_info") or {}
            best_video = None
            variants = ((info.get("video_info") or {}).get("variants")) or []
            mp4s = [
                v
                for v in variants
                if isinstance(v, dict) and v.get("content_type") == "video/mp4"
            ]
            if mp4s:
                mp4s.sort(key=lambda v: _coerce_int(v.get("bitrate")) or 0, reverse=True)
                best_video = mp4s[0].get("url")
            out.append(
                Media(
                    kind="gif" if typename == "ApiGif" else "video",
                    url=upgrade_image_url(thumb),
                    alt=info.get("ext_alt_text") or "",
                    width=_coerce_int(original.get("width")),
                    height=_coerce_int(original.get("height")),
                    video_url=best_video,
                )
            )
    return out


def entity_map_by_key(entity_map: Sequence[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Index an article ``entityMap`` by its ``key`` field.

    The ``entityMap`` array is *not* stored in key order -- the ``key`` values are a
    permutation of the array positions (verified against live article payloads), so
    looking an entity up by array index silently pairs the wrong URL with a label.
    """
    by_key: Dict[int, Dict[str, Any]] = {}
    for position, entry in enumerate(entity_map or []):
        if not isinstance(entry, dict):
            continue
        raw_key = entry.get("key")
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            key = position
        by_key.setdefault(key, entry)
    return by_key


def _inline_entities_to_markdown(
    block: ArticleBlock, by_key: Dict[int, Dict[str, Any]]
) -> str:
    """Apply inline ``entityRanges`` (links, markdown snippets) to a block's text."""
    text = block.text or ""
    if not block.entity_ranges:
        return escape_text(text)
    spans: List[Tuple[int, int, str]] = []
    for rng in block.entity_ranges:
        if not isinstance(rng, dict):
            continue
        key = rng.get("key")
        offset = rng.get("offset")
        length = rng.get("length")
        if not isinstance(key, int) or not isinstance(offset, int) or not isinstance(length, int):
            continue
        entity = by_key.get(key)
        if entity is None:
            continue
        etype = ((entity.get("value") or {}).get("type")) or ""
        data = ((entity.get("value") or {}).get("data")) or {}
        bounds = _facet_slice(text, offset, offset + length)
        if bounds is None:
            continue
        start, end = bounds

        if etype == "LINK":
            url = data.get("url")
            if not url:
                continue
            visible = text[start:end]
            if not visible.strip():
                # Some LINK entities are anchored to a single space; render the
                # target as a bare autolink instead of an empty label.
                spans.append((start, end, "<%s>" % escape_markdown_url(str(url))))
            else:
                spans.append(
                    (
                        start,
                        end,
                        "[%s](%s)"
                        % (
                            escape_markdown_link_text(visible),
                            escape_markdown_url(str(url)),
                        ),
                    )
                )
        elif etype == "MARKDOWN":
            raw = data.get("markdown")
            if raw:
                # Author-supplied Markdown: keep the syntax, neutralise HTML tags.
                spans.append((start, end, neutralise_raw_html(str(raw))))
        elif etype == "DIVIDER":
            spans.append((start, end, ""))
    return splice_spans(text, spans)


def render_article(article: Article) -> List[str]:
    """Render a Draft.js article body as real Markdown structure."""
    lines: List[str] = []
    by_key = entity_map_by_key(article.entity_map)
    list_counter = 0

    for block in article.blocks:
        btype = block.type or "unstyled"

        if btype == "atomic":
            for rng in block.entity_ranges or []:
                key = rng.get("key") if isinstance(rng, dict) else None
                if not isinstance(key, int):
                    continue
                entity = by_key.get(key)
                if entity is None:
                    continue
                etype = ((entity.get("value") or {}).get("type")) or ""
                data = ((entity.get("value") or {}).get("data")) or {}
                if etype == "MEDIA":
                    media = _media_from_article_entity(entity, article.media_entities)
                    rendered = render_media_list(media, heading=None)
                    if rendered:
                        lines.extend(rendered)
                        lines.append("")
                elif etype == "TWEET":
                    tweet_id = str(data.get("tweetId") or "")
                    if tweet_id:
                        url = "https://x.com/i/status/%s" % tweet_id
                        lines.extend(
                            blockquote(
                                "**Embedded post** — <%s>" % escape_markdown_url(url)
                            )
                        )
                        lines.append("")
                elif etype == "DIVIDER":
                    lines.append("---")
                    lines.append("")
                elif etype == "MARKDOWN":
                    raw = data.get("markdown")
                    if raw:
                        lines.append(neutralise_raw_html(str(raw)))
                        lines.append("")
            continue

        text = _inline_entities_to_markdown(block, by_key)

        if btype in _ARTICLE_HEADING_LEVELS:
            lines.append("%s %s" % (_ARTICLE_HEADING_LEVELS[btype], single_line(text)))
            lines.append("")
            list_counter = 0
        elif btype == "unordered-list-item":
            lines.append("- %s" % text)
            list_counter = 0
        elif btype == "ordered-list-item":
            list_counter += 1
            lines.append("%d. %s" % (list_counter, text))
        elif btype == "blockquote":
            lines.extend(blockquote(text))
            lines.append("")
            list_counter = 0
        elif btype == "code-block":
            lines.append("```")
            lines.extend((block.text or "").split("\n"))
            lines.append("```")
            lines.append("")
            list_counter = 0
        elif btype.startswith("header"):
            lines.append("#### %s" % single_line(text))
            lines.append("")
            list_counter = 0
        else:  # unstyled and anything unknown
            if text.strip():
                lines.extend(hard_breaks(text).split("\n"))
                lines.append("")
            list_counter = 0

    while lines and lines[-1] == "":
        lines.pop()
    return lines


# --------------------------------------------------------------------------- #
# Frontmatter + document rendering
# --------------------------------------------------------------------------- #


def build_frontmatter(doc: Document, post: Post) -> List[str]:
    lines = ["---"]
    lines.append("source: %s" % yaml_scalar(post.url or doc.source_url))
    lines.append("tweet_id: %s" % yaml_scalar(post.post_id or doc.status_id))
    lines.append("author_name: %s" % yaml_scalar(post.author.name))
    lines.append("author_handle: %s" % yaml_scalar(post.author.handle))
    lines.append("author_url: %s" % yaml_scalar(post.author.url))
    lines.append("posted_at: %s" % yaml_scalar(post.created_at))
    lines.append("kind: %s" % yaml_scalar(doc.kind))
    lines.append("provider: %s" % yaml_scalar(doc.provider))
    if doc.kind == "thread":
        lines.append("thread_length: %d" % len(doc.posts))
        lines.append("thread_complete: %s" % yaml_scalar(doc.thread_complete))
    if post.lang:
        lines.append("lang: %s" % yaml_scalar(post.lang))
    stats = [
        ("likes", post.likes),
        ("retweets", post.retweets),
        ("replies", post.replies),
        ("views", post.views),
        ("quotes", post.quotes),
        ("bookmarks", post.bookmarks),
    ]
    for key, value in stats:
        if value is not None:
            lines.append("%s: %d" % (key, value))
    if doc.warnings:
        lines.append("warnings:")
        for warning in doc.warnings:
            lines.append("  - %s" % yaml_scalar(warning))
    lines.append("---")
    return lines


def render_document(doc: Document) -> str:
    primary = doc.primary
    out: List[str] = []
    out.extend(build_frontmatter(doc, primary))
    out.append("")

    if doc.kind == "article" and primary.article:
        article = primary.article
        out.append("# %s" % single_line(escape_text(article.title or "Untitled article")))
        out.append("")
        byline_bits = [single_line(escape_text(primary.author.byline))]
        if primary.created_at:
            byline_bits.append(primary.created_at)
        byline_bits.append("<%s>" % escape_markdown_url(primary.url or doc.source_url))
        out.append("*%s*" % " · ".join(byline_bits))
        out.append("")
        if article.preview_text and article.preview_text.strip():
            out.append("> %s" % escape_text(article.preview_text.strip()))
            out.append("")
        if article.cover and article.cover.url:
            out.append("![%s](%s)" % ("cover image", escape_markdown_url(article.cover.url)))
            out.append("")
        out.extend(render_article(article))
        out.append("")
        if primary.media:
            out.extend(render_media_list(primary.media))
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    if doc.kind == "thread":
        total = len(doc.posts)
        out.append("# Thread by %s" % single_line(escape_text(primary.author.byline)))
        out.append("")
        if not doc.thread_complete:
            out.append(
                "> **Warning:** this thread is incomplete. %s"
                % escape_text(" ".join(doc.warnings) or "Not all posts could be retrieved.")
            )
            out.append("")
        for index, post in enumerate(doc.posts, start=1):
            out.append("## %d/%d" % (index, total))
            out.append("")
            if post.text:
                out.extend(hard_breaks(post.text).split("\n"))
                out.append("")
            if post.media:
                out.extend(render_media_list(post.media))
                out.append("")
            if post.poll:
                out.extend(render_poll(post.poll))
                out.append("")
            if post.quote:
                out.append("**Quoted post**")
                out.append("")
                out.extend(render_quote(post.quote))
                out.append("")
            meta = []
            if post.created_at:
                meta.append(post.created_at)
            if post.url:
                meta.append("<%s>" % escape_markdown_url(post.url))
            if meta:
                out.append("*%s*" % " · ".join(meta))
                out.append("")
        return "\n".join(out).rstrip() + "\n"

    # single post
    out.append("# Post by %s" % single_line(escape_text(primary.author.byline)))
    out.append("")
    if not doc.thread_complete:
        out.append(
            "> **Warning:** this post is part of a thread that could not be "
            "fully retrieved. %s"
            % escape_text(" ".join(doc.warnings))
        )
        out.append("")
    if primary.text:
        out.extend(hard_breaks(primary.text).split("\n"))
        out.append("")
    if primary.media:
        out.extend(render_media_list(primary.media))
        out.append("")
    if primary.poll:
        out.extend(render_poll(primary.poll))
        out.append("")
    if primary.quote:
        out.append("**Quoted post**")
        out.append("")
        out.extend(render_quote(primary.quote))
        out.append("")
    meta_bits = []
    if primary.created_at:
        meta_bits.append(primary.created_at)
    meta_bits.append("<%s>" % escape_markdown_url(primary.url or doc.source_url))
    out.append("*%s*" % " · ".join(meta_bits))
    return "\n".join(out).rstrip() + "\n"


def document_to_json(doc: Document) -> Dict[str, Any]:
    def post_to_dict(post: Optional[Post], depth: int = 0) -> Any:
        if post is None or depth > 4:
            return None
        return {
            "tweet_id": post.post_id,
            "url": post.url,
            "text": post.text,
            "posted_at": post.created_at,
            "lang": post.lang,
            "is_note_tweet": post.is_note_tweet,
            "is_self_reply": post.is_self_reply,
            "author": dataclasses.asdict(post.author),
            "stats": {
                key: value
                for key, value in (
                    ("likes", post.likes),
                    ("retweets", post.retweets),
                    ("replies", post.replies),
                    ("views", post.views),
                    ("quotes", post.quotes),
                    ("bookmarks", post.bookmarks),
                )
                if value is not None
            },
            "media": [dataclasses.asdict(m) for m in post.media],
            "poll": dataclasses.asdict(post.poll) if post.poll else None,
            "quote": post_to_dict(post.quote, depth + 1),
            "article": (
                {
                    "id": post.article.article_id,
                    "title": post.article.title,
                    "preview_text": post.article.preview_text,
                    "created_at": post.article.created_at,
                    "modified_at": post.article.modified_at,
                    "block_count": len(post.article.blocks),
                }
                if post.article
                else None
            ),
        }

    return {
        "kind": doc.kind,
        "source_url": doc.source_url,
        "status_id": doc.status_id,
        "provider": doc.provider,
        "thread_complete": doc.thread_complete,
        "warnings": doc.warnings,
        "author": dataclasses.asdict(doc.author),
        "posts": [post_to_dict(p) for p in doc.posts],
    }


# --------------------------------------------------------------------------- #
# Shared normalization helpers
# --------------------------------------------------------------------------- #


def _author_from(obj: Any, handle_key: str = "screen_name") -> Author:
    if not isinstance(obj, dict):
        return Author()
    handle = str(obj.get(handle_key) or obj.get("username") or "")
    return Author(
        name=str(obj.get("name") or ""),
        handle=handle,
        url=str(obj.get("url") or (("https://x.com/%s" % handle) if handle else "")),
        author_id=str(obj.get("id") or obj.get("id_str") or ""),
    )


def _stats_from(obj: Dict[str, Any]) -> Dict[str, Optional[int]]:
    return {
        "likes": _coerce_int(obj.get("likes") if "likes" in obj else obj.get("favorite_count")),
        "retweets": _coerce_int(obj.get("reposts") if "reposts" in obj else obj.get("retweet_count")),
        "replies": _coerce_int(
            obj.get("replies") if "replies" in obj else obj.get("reply_count") or obj.get("conversation_count")
        ),
        "views": _coerce_int(obj.get("views") if "views" in obj else obj.get("view_count")),
        "quotes": _coerce_int(obj.get("quotes") if "quotes" in obj else obj.get("quote_count")),
        "bookmarks": _coerce_int(obj.get("bookmarks") if "bookmarks" in obj else obj.get("bookmark_count")),
    }


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #


class Provider:
    """A retrieval strategy."""

    name = "provider"
    supports_threads = False
    supports_articles = False

    def __init__(self, client: HttpClient, options: Optional[Dict[str, Any]] = None) -> None:
        self.client = client
        self.options = options or {}

    def available(self) -> Optional[str]:
        """Return a reason string when the provider cannot run, else ``None``."""
        return None

    def fetch(self, target: Target) -> Document:  # pragma: no cover - interface
        raise NotImplementedError


def _document_from_fxtwitter_payload(
    payload: Dict[str, Any], target: Target, provider: str
) -> Document:
    """Normalize an FxTwitter v2 ``/2/status`` or ``/2/thread`` payload."""
    status = payload.get("status")
    if not isinstance(status, dict):
        code = payload.get("code")
        message = payload.get("message") or "no status object in response"
        raise ProviderError(provider, str(message), status=code if isinstance(code, int) else None)

    thread_items = payload.get("thread") or []
    posts: List[Post] = []
    if isinstance(thread_items, list):
        for item in thread_items:
            if isinstance(item, dict) and item.get("id"):
                posts.append(_post_from_fxtwitter(item))
    focal = _post_from_fxtwitter(status)
    if not posts:
        posts = [focal]

    document = Document(
        source_url=target.display_url,
        status_id=target.status_id,
        author=focal.author,
        posts=posts,
        provider=provider,
    )
    if focal.article:
        document.kind = "article"
        document.posts = [focal]
    elif len(posts) > 1:
        document.kind = "thread"
    else:
        document.kind = "post"
    if focal.is_self_reply and len(posts) == 1:
        document.kind = "thread"
        document.thread_complete = False
        document.warnings.append(
            "this post replies to its own author, so it is part of a thread, but "
            "the thread listing returned only this post"
        )
    return document


def _post_from_fxtwitter(data: Dict[str, Any]) -> Post:
    post = Post()
    post.post_id = str(data.get("id") or "")
    post.url = str(data.get("url") or "")
    post.lang = str(data.get("lang") or "")
    post.is_note_tweet = bool(data.get("is_note_tweet"))
    post.created_at = to_iso8601(data.get("created_at") or data.get("created_timestamp"))
    post.author = _author_from(data.get("author"))

    raw_text = data.get("raw_text") or {}
    raw_value = raw_text.get("text") if isinstance(raw_text, dict) else None
    source_text = raw_value if raw_value is not None else (data.get("text") or "")
    facets = raw_text.get("facets") if isinstance(raw_text, dict) else None
    post.facets = facets if isinstance(facets, list) else []
    post.text = render_text_with_facets(str(source_text or ""), post.facets)

    replying_to = data.get("replying_to")
    if isinstance(replying_to, dict) and replying_to.get("screen_name"):
        post.is_self_reply = str(replying_to.get("screen_name")).lower() == post.author.handle.lower()

    stats = _stats_from(data)
    post.likes = stats["likes"]
    post.retweets = stats["retweets"]
    post.replies = stats["replies"]
    post.views = stats["views"]
    post.quotes = stats["quotes"]
    post.bookmarks = stats["bookmarks"]

    post.media = _media_from_fxtwitter(data.get("media"))

    poll = data.get("poll")
    if isinstance(poll, dict) and poll.get("choices"):
        choices = []
        for choice in poll["choices"]:
            if not isinstance(choice, dict):
                continue
            choices.append(
                PollChoice(
                    label=str(choice.get("label") or ""),
                    count=_coerce_int(choice.get("count")),
                    percentage=(
                        float(choice["percentage"])
                        if isinstance(choice.get("percentage"), (int, float))
                        else None
                    ),
                )
            )
        post.poll = Poll(
            choices=choices,
            total_votes=_coerce_int(poll.get("total_votes")),
            ends_at=to_iso8601(poll.get("ends_at")),
        )

    quote = data.get("quote")
    if isinstance(quote, dict) and quote.get("id") and quote.get("author"):
        post.quote = _post_from_fxtwitter(quote)

    article = data.get("article")
    if isinstance(article, dict) and (article.get("content") or article.get("title")):
        post.article = _article_from_fxtwitter(article)
    return post


def _media_from_fxtwitter(media: Any) -> List[Media]:
    if not isinstance(media, dict):
        return []
    out: List[Media] = []
    for photo in media.get("photos") or []:
        if not isinstance(photo, dict):
            continue
        out.append(
            Media(
                kind="image" if photo.get("type") != "gif" else "gif",
                url=upgrade_image_url(str(photo.get("url") or "")),
                alt=str(photo.get("altText") or ""),
                width=_coerce_int(photo.get("width")),
                height=_coerce_int(photo.get("height")),
            )
        )
    for video in media.get("videos") or []:
        if not isinstance(video, dict):
            continue
        out.append(
            Media(
                kind="gif" if video.get("type") == "gif" else "video",
                url=upgrade_image_url(str(video.get("thumbnail_url") or "")),
                alt=str(video.get("altText") or ""),
                width=_coerce_int(video.get("width")),
                height=_coerce_int(video.get("height")),
                video_url=str(video.get("url") or "") or None,
                duration=(
                    float(video["duration"])
                    if isinstance(video.get("duration"), (int, float))
                    else None
                ),
            )
        )
    external = media.get("external")
    if isinstance(external, dict) and external.get("url"):
        out.append(
            Media(
                kind="video" if external.get("type") == "video" else "image",
                url=upgrade_image_url(str(external.get("thumbnail_url") or external["url"])),
                alt=str(external.get("altText") or ""),
                width=_coerce_int(external.get("width")),
                height=_coerce_int(external.get("height")),
                video_url=str(external.get("url")),
            )
        )
    return [m for m in out if m.url]


def _article_from_fxtwitter(article: Dict[str, Any]) -> Article:
    content = article.get("content") or {}
    blocks: List[ArticleBlock] = []
    for block in content.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        blocks.append(
            ArticleBlock(
                type=str(block.get("type") or "unstyled"),
                text=str(block.get("text") or ""),
                entity_ranges=list(block.get("entityRanges") or []),
                inline_style_ranges=list(block.get("inlineStyleRanges") or []),
            )
        )
    cover = None
    cover_raw = article.get("cover_media")
    if isinstance(cover_raw, dict):
        info = cover_raw.get("media_info") or {}
        if info.get("__typename") == "ApiImage" and info.get("original_img_url"):
            cover = Media(
                kind="image",
                url=upgrade_image_url(str(info["original_img_url"])),
                width=_coerce_int(info.get("original_img_width")),
                height=_coerce_int(info.get("original_img_height")),
            )
    return Article(
        article_id=str(article.get("id") or ""),
        title=str(article.get("title") or ""),
        preview_text=str(article.get("preview_text") or ""),
        created_at=to_iso8601(article.get("created_at")),
        modified_at=to_iso8601(article.get("modified_at")),
        cover=cover,
        blocks=blocks,
        entity_map=list(content.get("entityMap") or []),
        media_entities=list(article.get("media_entities") or []),
    )


class FxTwitterProvider(Provider):
    """No-auth JSON mirror (FxTwitter / FixupX). Richest source: threads + articles."""

    name = "fxtwitter"
    supports_threads = True
    supports_articles = True
    BASE = "https://api.fxtwitter.com"

    def fetch(self, target: Target) -> Document:
        payload = self._fetch_json("%s/2/thread/%s" % (self.BASE, target.status_id))
        status = payload.get("status")
        if not isinstance(status, dict) or not status.get("id"):
            # Fall back to the single-post endpoint; some posts have no thread listing.
            payload = self._fetch_json("%s/2/status/%s" % (self.BASE, target.status_id))
        return _document_from_fxtwitter_payload(payload, target, self.name)

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        resp = self.client.request(url, provider=self.name)
        if resp.status != 200:
            message = "request failed"
            try:
                err = _require_json(resp, self.name)
                if isinstance(err, dict):
                    message = str(err.get("message") or err.get("error") or message)
            except ProviderError:
                message = "request failed with HTTP %s" % resp.status
            raise ProviderError(self.name, message, url, resp.status)
        payload = _require_json(resp, self.name)
        if not isinstance(payload, dict):
            raise ProviderError(self.name, "unexpected payload shape", url, resp.status)
        code = payload.get("code")
        if isinstance(code, int) and code != 200:
            raise ProviderError(
                self.name,
                str(payload.get("message") or "provider returned code %s" % code),
                url,
                resp.status,
            )
        return payload


class VxTwitterProvider(Provider):
    """No-auth JSON mirror (vxTwitter / FixTweet). Single posts only."""

    name = "vxtwitter"
    supports_threads = False
    supports_articles = False
    BASE = "https://api.vxtwitter.com"

    def fetch(self, target: Target) -> Document:
        path = target.handle or "i"
        url = "%s/%s/status/%s" % (self.BASE, urllib.parse.quote(path), target.status_id)
        resp = self.client.request(url, provider=self.name)
        if resp.status != 200:
            raise ProviderError(
                self.name, "request failed with HTTP %s" % resp.status, url, resp.status
            )
        payload = _require_json(resp, self.name)
        if not isinstance(payload, dict) or not payload.get("tweetID"):
            raise ProviderError(self.name, "response missing tweetID", url, resp.status)
        return _document_from_vxtwitter_payload(payload, target, self.name)


def _document_from_vxtwitter_payload(
    payload: Dict[str, Any], target: Target, provider: str
) -> Document:
    post = Post()
    post.post_id = str(payload.get("tweetID") or target.status_id)
    post.url = "https://x.com/%s/status/%s" % (
        payload.get("user_screen_name") or "i",
        post.post_id,
    )
    post.lang = str(payload.get("lang") or "")
    post.created_at = to_iso8601(payload.get("date") or payload.get("date_epoch"))
    handle = str(payload.get("user_screen_name") or "")
    post.author = Author(
        name=str(payload.get("user_name") or ""),
        handle=handle,
        url="https://x.com/%s" % handle if handle else "",
    )
    post.text = escape_text(str(payload.get("text") or ""))
    stats = _stats_from(payload)
    post.likes = stats["likes"]
    post.retweets = stats["retweets"]
    post.replies = stats["replies"]
    post.views = stats["views"]

    for item in payload.get("media_extended") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        kind = str(item.get("type") or "image")
        size = item.get("size") or {}
        thumb = item.get("thumbnail_url") or item.get("url")
        post.media.append(
            Media(
                kind="video" if kind == "video" else ("gif" if kind == "gif" else "image"),
                url=upgrade_image_url(str(thumb)),
                alt=str(item.get("altText") or ""),
                width=_coerce_int(size.get("width")),
                height=_coerce_int(size.get("height")),
                video_url=str(item.get("url")) if kind == "video" else None,
                duration=(
                    float(item["duration_millis"]) / 1000.0
                    if isinstance(item.get("duration_millis"), (int, float))
                    else None
                ),
            )
        )

    poll_data = payload.get("pollData")
    if isinstance(poll_data, dict) and poll_data.get("choices"):
        choices = [
            PollChoice(
                label=str(c.get("label") or ""),
                count=_coerce_int(c.get("count")),
                percentage=(
                    float(c["percentage"])
                    if isinstance(c.get("percentage"), (int, float))
                    else None
                ),
            )
            for c in poll_data["choices"]
            if isinstance(c, dict)
        ]
        post.poll = Poll(choices=choices, total_votes=_coerce_int(poll_data.get("total_votes")))

    qrt = payload.get("qrt")
    if isinstance(qrt, dict) and qrt.get("tweetID"):
        q = Post()
        q.post_id = str(qrt.get("tweetID"))
        q.url = str(qrt.get("tweetURL") or "")
        q.text = escape_text(str(qrt.get("text") or ""))
        q.created_at = to_iso8601(qrt.get("date") or qrt.get("date_epoch"))
        qh = str(qrt.get("user_screen_name") or "")
        q.author = Author(
            name=str(qrt.get("user_name") or ""),
            handle=qh,
            url="https://x.com/%s" % qh if qh else "",
        )
        post.quote = q

    replying_to = payload.get("replyingToID")
    if replying_to and str(payload.get("replyingTo") or "").lower() == handle.lower():
        post.is_self_reply = True

    document = Document(
        source_url=target.display_url,
        status_id=target.status_id,
        author=post.author,
        posts=[post],
        provider=provider,
    )
    document.kind = "thread" if post.is_self_reply else "post"
    if post.is_self_reply:
        document.thread_complete = False
        document.warnings.append(
            "this post replies to its own author (so it is part of a thread), but "
            "provider '%s' cannot enumerate conversations; only this post was retrieved"
            % provider
        )
    return document


class SyndicationProvider(Provider):
    """X's public syndication endpoint. Single posts only, no auth, no token validation."""

    name = "syndication"
    supports_threads = False
    supports_articles = False
    BASE = "https://cdn.syndication.twimg.com/tweet-result"

    def fetch(self, target: Target) -> Document:
        params = urllib.parse.urlencode(
            {"id": target.status_id, "token": syndication_token(target.status_id), "lang": "en"}
        )
        url = "%s?%s" % (self.BASE, params)
        resp = self.client.request(url, provider=self.name)
        if resp.status != 200:
            raise ProviderError(
                self.name, "request failed with HTTP %s" % resp.status, url, resp.status
            )
        if not resp.body.strip():
            raise ProviderError(
                self.name,
                "empty response body (the post is unavailable, deleted or protected)",
                url,
                resp.status,
            )
        payload = _require_json(resp, self.name)
        if not isinstance(payload, dict) or not payload.get("id_str"):
            raise ProviderError(self.name, "response missing id_str", url, resp.status)
        return _document_from_syndication_payload(payload, target, self.name)


def _document_from_syndication_payload(
    payload: Dict[str, Any], target: Target, provider: str
) -> Document:
    post = Post()
    post.post_id = str(payload.get("id_str") or target.status_id)
    user = payload.get("user") or {}
    handle = str(user.get("screen_name") or "")
    post.url = "https://x.com/%s/status/%s" % (handle or "i", post.post_id)
    post.lang = str(payload.get("lang") or "")
    post.created_at = to_iso8601(payload.get("created_at"))
    post.author = Author(
        name=str(user.get("name") or ""),
        handle=handle,
        url="https://x.com/%s" % handle if handle else "",
        author_id=str(user.get("id_str") or ""),
    )
    note = payload.get("note_tweet") or {}
    note_text = note.get("text") if isinstance(note, dict) else None
    entities = (note.get("entity_set") if isinstance(note, dict) else None) or payload.get("entities") or {}
    post.is_note_tweet = bool(note_text)
    post.text = _render_syndication_text(str(note_text or payload.get("text") or ""), entities)
    stats = _stats_from(payload)
    post.likes = stats["likes"]
    post.retweets = stats["retweets"]
    post.replies = stats["replies"]

    post.media = _media_from_syndication(payload)

    quoted = payload.get("quoted_tweet")
    if isinstance(quoted, dict) and quoted.get("id_str"):
        q = Post()
        q.post_id = str(quoted.get("id_str"))
        qu = quoted.get("user") or {}
        qh = str(qu.get("screen_name") or "")
        q.url = "https://x.com/%s/status/%s" % (qh or "i", q.post_id)
        q.created_at = to_iso8601(quoted.get("created_at"))
        q.author = Author(
            name=str(qu.get("name") or ""), handle=qh, url="https://x.com/%s" % qh if qh else ""
        )
        q.text = _render_syndication_text(
            str(quoted.get("text") or ""), quoted.get("entities") or {}
        )
        q.media = _media_from_syndication(quoted)
        qstats = _stats_from(quoted)
        q.likes, q.retweets, q.replies = qstats["likes"], qstats["retweets"], qstats["replies"]
        post.quote = q

    document = Document(
        source_url=target.display_url,
        status_id=target.status_id,
        author=post.author,
        posts=[post],
        provider=provider,
    )
    document.kind = "post"
    return document


def _media_from_syndication(payload: Dict[str, Any]) -> List[Media]:
    out: List[Media] = []
    for photo in payload.get("photos") or []:
        if not isinstance(photo, dict):
            continue
        url = photo.get("url") or photo.get("media_url_https") or photo.get("media_url")
        if not url:
            continue
        out.append(
            Media(
                kind="image",
                url=upgrade_image_url(str(url)),
                alt=str(photo.get("altText") or photo.get("ext_alt_text") or ""),
                width=_coerce_int(photo.get("width")),
                height=_coerce_int(photo.get("height")),
            )
        )
    video = payload.get("video")
    if isinstance(video, dict):
        poster = video.get("poster") or ""
        best = None
        variants = video.get("variants") or []
        mp4s = [
            v
            for v in variants
            if isinstance(v, dict) and v.get("type") == "video/mp4" and v.get("src")
        ]
        if mp4s:
            best = mp4s[-1].get("src")
        if poster:
            # `aspectRatio` is a ratio (e.g. [16, 9]), not pixel dimensions, so it is
            # deliberately not reported as width/height.
            out.append(
                Media(
                    kind="video",
                    url=upgrade_image_url(str(poster)),
                    video_url=best,
                    duration=(
                        float(video["durationMs"]) / 1000.0
                        if isinstance(video.get("durationMs"), (int, float))
                        else None
                    ),
                )
            )
    for detail in payload.get("mediaDetails") or []:
        if not isinstance(detail, dict):
            continue
        url = detail.get("media_url_https")
        if not url:
            continue
        if any(m.url.split("?")[0] == str(url).split("?")[0] for m in out):
            continue
        kind = "video" if detail.get("type") == "video" else "image"
        out.append(
            Media(
                kind=kind,
                url=upgrade_image_url(str(url)),
                alt=str(detail.get("ext_alt_text") or ""),
                width=_coerce_int((detail.get("original_info") or {}).get("width")),
                height=_coerce_int((detail.get("original_info") or {}).get("height")),
            )
        )
    return [m for m in out if m.url]


def _render_syndication_text(text: str, entities: Dict[str, Any]) -> str:
    """Render syndication text, rewriting t.co links via the ``entities`` block."""
    if not text:
        return ""
    edits: List[Tuple[int, int, str]] = []
    for url_entity in (entities or {}).get("urls") or []:
        if not isinstance(url_entity, dict):
            continue
        indices = url_entity.get("indices")
        target = url_entity.get("expanded_url") or url_entity.get("url")
        display = url_entity.get("display_url")
        if not indices or not target or len(indices) != 2:
            continue
        start, end = int(indices[0]), int(indices[1])
        if start < 0 or end > len(text) or start >= end:
            continue
        visible = text[start:end]
        if display and display != visible:
            edits.append(
                (
                    start,
                    end,
                    "[%s](%s)"
                    % (escape_markdown_link_text(visible), escape_markdown_url(str(target))),
                )
            )
        else:
            edits.append((start, end, "<%s>" % escape_markdown_url(str(target))))
    out: List[str] = []
    pos = 0
    for start, end, repl in sorted(edits, key=lambda e: e[0]):
        out.append(escape_text(text[pos:start]))
        out.append(repl)
        pos = end
    out.append(escape_text(text[pos:]))
    return "".join(out)


class GraphQLProvider(Provider):
    """Guest/anonymous GraphQL ``TweetDetail`` conversation retrieval.

    UNVERIFIED against live traffic in this build. X requires a ``queryId`` that
    changes whenever the web client is redeployed; this provider takes the id from
    ``--graphql-query-id`` or ``$X2MD_GRAPHQL_QUERY_ID``. When no id is configured
    the provider reports that honestly instead of guessing, and the caller degrades
    to a clearly-labelled partial document.
    """

    name = "graphql"
    supports_threads = True
    supports_articles = False

    GUEST_ACTIVATE = "https://api.twitter.com/1.1/guest/activate.json"
    GRAPHQL_BASE = "https://api.x.com/graphql"
    OPERATION = "TweetDetail"

    def available(self) -> Optional[str]:
        if not self._query_id():
            return (
                "no GraphQL query id configured; pass --graphql-query-id or set "
                "$%s (X rotates this value with every web deploy)" % GRAPHQL_QUERY_ID_ENV
            )
        return None

    def _query_id(self) -> Optional[str]:
        explicit = self.options.get("query_id") or os.environ.get(GRAPHQL_QUERY_ID_ENV)
        if explicit:
            return str(explicit).strip() or None
        return None

    def _auth_headers(self) -> Dict[str, str]:
        bearer = os.environ.get("X2MD_BEARER_TOKEN", PUBLIC_WEB_BEARER)
        headers = {
            "Authorization": "Bearer %s" % bearer,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }
        auth_token = os.environ.get("X2MD_AUTH_TOKEN")
        ct0 = os.environ.get("X2MD_CT0")
        auth_file = self.options.get("auth_file")
        if auth_file and Path(auth_file).is_file():
            try:
                stored = json.loads(Path(auth_file).read_text(encoding="utf-8"))
            except (ValueError, OSError):
                stored = {}
            if isinstance(stored, dict):
                auth_token = auth_token or stored.get("auth_token")
                ct0 = ct0 or stored.get("ct0")
                if stored.get("bearer_token"):
                    headers["Authorization"] = "Bearer %s" % stored["bearer_token"]
        if auth_token and ct0:
            headers["Cookie"] = "auth_token=%s; ct0=%s" % (auth_token, ct0)
            headers["x-csrf-token"] = str(ct0)
        return headers

    def _guest_token(self) -> Optional[str]:
        if "Cookie" in self._auth_headers():
            return None
        # The Authorization bearer header is mandatory here: without it X returns
        # HTTP 403, with it HTTP 200 (verified counterfactually on 2026-09-18).
        resp = self.client.request(
            self.GUEST_ACTIVATE,
            method="POST",
            headers=self._auth_headers(),
            provider=self.name,
        )
        if resp.status != 200:
            raise ProviderError(
                self.name,
                "guest token activation failed with HTTP %s" % resp.status,
                self.GUEST_ACTIVATE,
                resp.status,
            )
        payload = _require_json(resp, self.name)
        token = payload.get("guest_token") if isinstance(payload, dict) else None
        if not token:
            raise ProviderError(
                self.name, "guest activation returned no guest_token", self.GUEST_ACTIVATE
            )
        return str(token)

    def fetch(self, target: Target) -> Document:
        reason = self.available()
        if reason:
            raise ProviderError(self.name, reason)
        query_id = self._query_id()
        headers = self._auth_headers()
        guest = self._guest_token()
        if guest:
            headers["x-guest-token"] = guest

        variables = {
            "focalTweetId": target.status_id,
            "with_rux_injections": False,
            "includePromotedContent": False,
            "withCommunity": True,
            "withBirdwatchNotes": True,
            "withVoice": True,
        }
        url = "%s/%s/%s?%s" % (
            self.GRAPHQL_BASE,
            query_id,
            self.OPERATION,
            urllib.parse.urlencode({"variables": json.dumps(variables)}),
        )
        resp = self.client.request(url, headers=headers, provider=self.name)
        if resp.status != 200:
            raise ProviderError(
                self.name,
                "TweetDetail failed with HTTP %s "
                "(the query id is likely stale, or the request is unauthorised)"
                % resp.status,
                url,
                resp.status,
            )
        payload = _require_json(resp, self.name)
        if isinstance(payload, dict) and payload.get("errors"):
            messages = "; ".join(
                str(e.get("message")) for e in payload["errors"] if isinstance(e, dict)
            )
            raise ProviderError(self.name, "GraphQL errors: %s" % messages, url, resp.status)
        return _document_from_graphql_payload(payload, target, self.name)


def _document_from_graphql_payload(
    payload: Dict[str, Any], target: Target, provider: str
) -> Document:
    """Normalize a ``TweetDetail`` response (instruction entries -> posts)."""
    records: List[Dict[str, Any]] = []
    instructions = (
        ((payload.get("data") or {}).get("threaded_conversation_with_injections_v2") or {})
        .get("instructions")
        or []
    )
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        for entry in instruction.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content") or {}
            # A TimelineTimelineItem carries itemContent directly; a module carries
            # it nested under items[].item. Handle both shapes.
            items = content.get("items") or [content]
            for item in items:
                if not isinstance(item, dict):
                    continue
                node = item.get("item") if isinstance(item.get("item"), dict) else item
                item_content = node.get("itemContent") or {}
                tweet = (item_content.get("tweet_results") or {}).get("result")
                if not isinstance(tweet, dict):
                    continue
                if tweet.get("__typename") == "TweetWithVisibilityResults":
                    tweet = tweet.get("tweet") or {}
                if tweet.get("rest_id"):
                    records.append(tweet)

    if not records:
        raise ProviderError(
            provider,
            "response contained no tweet entries (unexpected shape, or the post is unavailable)",
        )

    posts = [_post_from_graphql(record) for record in records]
    focal = None
    for post in posts:
        if post.post_id == target.status_id:
            focal = post
            break
    if focal is None:
        focal = posts[0]
    document = Document(
        source_url=target.display_url,
        status_id=target.status_id,
        author=focal.author,
        posts=posts,
        provider=provider,
    )
    if len(posts) > 1:
        document.kind = "thread"
    else:
        document.kind = "post"
    if focal.is_self_reply and len(posts) == 1:
        document.kind = "thread"
        document.thread_complete = False
        document.warnings.append(
            "GraphQL returned only a single post for a self-reply; the thread may be incomplete"
        )
    return document


def _post_from_graphql(record: Dict[str, Any]) -> Post:
    legacy = record.get("legacy") or {}
    core = record.get("core") or {}
    user_core = core.get("user_results", {}).get("result", {}) if isinstance(core, dict) else {}
    user_legacy = (user_core or {}).get("legacy") or {}
    if not user_legacy and isinstance(user_core, dict):
        user_legacy = user_core.get("core") or {}

    post = Post()
    post.post_id = str(record.get("rest_id") or legacy.get("id_str") or "")
    handle = str(user_legacy.get("screen_name") or "")
    post.author = Author(
        name=str(user_legacy.get("name") or ""),
        handle=handle,
        url="https://x.com/%s" % handle if handle else "",
        author_id=str(user_legacy.get("id_str") or ""),
    )
    post.url = "https://x.com/%s/status/%s" % (handle or "i", post.post_id)
    post.lang = str(legacy.get("lang") or "")
    post.created_at = to_iso8601(legacy.get("created_at"))

    note = (record.get("note_tweet") or {}).get("note_tweet_results", {}).get("result")
    if isinstance(note, dict) and note.get("text"):
        post.is_note_tweet = True
        post.text = escape_text(str(note.get("text")))
    else:
        post.text = escape_text(str(legacy.get("full_text") or ""))

    post.likes = _coerce_int(legacy.get("favorite_count"))
    post.retweets = _coerce_int(legacy.get("retweet_count"))
    post.replies = _coerce_int(legacy.get("reply_count"))
    post.quotes = _coerce_int(legacy.get("quote_count"))
    post.bookmarks = _coerce_int(legacy.get("bookmark_count"))
    views = (record.get("views") or {}).get("count")
    post.views = _coerce_int(views)

    reply_handle = str(legacy.get("in_reply_to_screen_name") or "")
    if reply_handle and handle and reply_handle.lower() == handle.lower():
        post.is_self_reply = True

    for item in (legacy.get("extended_entities") or legacy.get("entities") or {}).get("media") or []:
        if not isinstance(item, dict):
            continue
        original = item.get("original_info") or {}
        kind = str(item.get("type") or "photo")
        if kind == "photo":
            post.media.append(
                Media(
                    kind="image",
                    url=upgrade_image_url(str(item.get("media_url_https") or "")),
                    alt=str(item.get("ext_alt_text") or ""),
                    width=_coerce_int(original.get("width")),
                    height=_coerce_int(original.get("height")),
                )
            )
        else:
            info = item.get("video_info") or {}
            mp4s = [
                v
                for v in info.get("variants") or []
                if isinstance(v, dict) and v.get("content_type") == "video/mp4"
            ]
            mp4s.sort(key=lambda v: _coerce_int(v.get("bitrate")) or 0, reverse=True)
            post.media.append(
                Media(
                    kind="video" if kind == "video" else "gif",
                    url=upgrade_image_url(str(item.get("media_url_https") or "")),
                    alt=str(item.get("ext_alt_text") or ""),
                    width=_coerce_int(original.get("width")),
                    height=_coerce_int(original.get("height")),
                    video_url=(mp4s[0].get("url") if mp4s else None),
                )
            )

    quoted = record.get("quoted_status_result", {}).get("result")
    if isinstance(quoted, dict) and quoted.get("rest_id"):
        if quoted.get("__typename") == "TweetWithVisibilityResults":
            quoted = quoted.get("tweet") or quoted
        if quoted.get("rest_id"):
            try:
                post.quote = _post_from_graphql(quoted)
            except Exception:  # pragma: no cover - defensive
                post.quote = None
    return post


# --------------------------------------------------------------------------- #
# Syndication token
# --------------------------------------------------------------------------- #


_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def js_tostring_base36(value: float) -> str:
    """Emulate ``Number.prototype.toString(36)`` for the X syndication token.

    V8 renders a double in a non-decimal radix exactly. Because every double is
    a dyadic rational and 36 = 2^2 * 3^2, that expansion terminates, so the exact
    conversion below is deterministic and reproducible.
    """
    exact = Fraction(float(value))
    negative = exact < 0
    exact = abs(exact)
    integer_part = int(exact)
    remainder = exact - integer_part

    if integer_part == 0:
        head = "0"
    else:
        digits = ""
        n = integer_part
        while n:
            n, r = divmod(n, 36)
            digits = _B36[r] + digits
        head = digits

    frac_digits: List[str] = []
    guard = 0
    while remainder != 0 and guard < 400:
        remainder *= 36
        digit = int(remainder)
        frac_digits.append(_B36[digit])
        remainder -= digit
        guard += 1

    out = head + ("." + "".join(frac_digits) if frac_digits else "")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return ("-" if negative else "") + out


def syndication_token(tweet_id: str) -> str:
    """Compute the syndication ``token`` query parameter for a status id.

    Note: as observed on 2026-09-18, ``cdn.syndication.twimg.com`` does not
    validate this value -- any non-empty token returns the post. The value is
    computed properly anyway so the request stays correct if validation returns.
    """
    try:
        numeric = int(str(tweet_id))
    except (TypeError, ValueError):
        return "x2md"
    value = (numeric / 1e15) * math.pi
    token = re.sub(r"(0+|\.)", "", js_tostring_base36(value))
    return token or "x2md"


# --------------------------------------------------------------------------- #
# Provider registry
# --------------------------------------------------------------------------- #

PROVIDER_CLASSES: List[Callable[..., Provider]] = [
    FxTwitterProvider,
    VxTwitterProvider,
    SyndicationProvider,
    GraphQLProvider,
]

PROVIDER_NAMES = ["auto"] + [cls.name for cls in PROVIDER_CLASSES]


def build_providers(
    provider: str, client: HttpClient, options: Optional[Dict[str, Any]] = None
) -> List[Provider]:
    """Instantiate the provider chain for ``--provider``."""
    options = options or {}
    if provider == "auto":
        return [cls(client, options) for cls in PROVIDER_CLASSES]
    for cls in PROVIDER_CLASSES:
        if cls.name == provider:
            return [cls(client, options)]
    raise InputError(
        "unknown provider %r; choose from: %s" % (provider, ", ".join(PROVIDER_NAMES))
    )


def fetch_document(
    target: Target,
    providers: Sequence[Provider],
    client: HttpClient,
    debug: bool = False,
    stream=None,
) -> Tuple[Document, List[ProviderError]]:
    """Run the provider chain, returning the first success plus any failures."""
    stream = stream if stream is not None else sys.stderr
    errors: List[ProviderError] = []
    for provider in providers:
        reason = provider.available()
        if reason:
            errors.append(ProviderError(provider.name, reason))
            if debug:
                print(
                    "[debug] %s skipped: %s" % (provider.name, reason),
                    file=stream,
                    flush=True,
                )
            continue
        try:
            document = provider.fetch(target)
        except ProviderError as exc:
            errors.append(exc)
            if debug:
                print("[debug] %s failed: %s" % (provider.name, exc.describe()), file=stream, flush=True)
            continue
        if not provider.supports_threads and document.kind != "article":
            document.warnings.append(
                "provider '%s' cannot enumerate threads; output is limited to the "
                "single post that was requested" % provider.name
            )
        return document, errors
    raise NoProviderAvailable(errors)


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #


def default_filename(doc: Document) -> str:
    handle = doc.primary.author.handle or "x"
    safe_handle = re.sub(r"[^A-Za-z0-9_]", "", handle) or "x"
    return "%s_%s.md" % (safe_handle, doc.status_id)


def write_output(text: str, path: Optional[str], outdir: Optional[str], filename: str) -> str:
    """Write ``text`` and return a human-readable destination description."""
    if path == "-":
        sys.stdout.write(text)
        return "stdout"
    if path:
        destination = Path(path)
    else:
        directory = Path(outdir) if outdir else Path.cwd()
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return str(destination)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Download an X (Twitter) post, self-thread or long-form X Article and "
            "convert it to clean Markdown."
        ),
        epilog=(
            "examples:\n"
            "  python3 x2md.py https://x.com/jack/status/20\n"
            "  python3 x2md.py 20 -o post.md\n"
            "  python3 x2md.py https://mobile.x.com/XCreators/status/2072439205213421694 --outdir out/\n"
            "  python3 x2md.py https://x.com/XBusiness/status/2097390372670575039 --json\n"
            "\n"
            "auth (all optional; the tool works with none):\n"
            "  X2MD_BEARER_TOKEN   bearer token for the graphql provider\n"
            "  X2MD_AUTH_TOKEN     auth_token cookie value\n"
            "  X2MD_CT0            ct0 csrf cookie value\n"
            "  X2MD_GRAPHQL_QUERY_ID  TweetDetail query id for the graphql provider\n"
            "  X2MD_AUTH_FILE      path to a JSON file holding auth_token/ct0/bearer_token\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls",
        nargs="+",
        metavar="URL_OR_ID",
        help="one or more X/Twitter post URLs (x.com, twitter.com, mobile./www. variants) or bare status ids",
    )
    parser.add_argument("-o", "--output", metavar="FILE", help="write to FILE (use '-' for stdout)")
    parser.add_argument("--outdir", metavar="DIR", help="write <handle>_<id>.md into DIR")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit normalized JSON instead of Markdown",
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default="auto",
        help="force one retrieval strategy instead of trying them in order (default: auto)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print the endpoint used and the raw HTTP status of every request to stderr",
    )
    parser.add_argument(
        "--graphql-query-id",
        metavar="ID",
        help="TweetDetail query id for the graphql provider (overrides $%s)" % GRAPHQL_QUERY_ID_ENV,
    )
    parser.add_argument(
        "--auth-file",
        metavar="FILE",
        help="JSON file with auth_token / ct0 / bearer_token for the graphql provider",
    )
    parser.add_argument(
        "--user-agent",
        metavar="UA",
        default=DEFAULT_UA,
        help=(
            "User-Agent header to send (default: %s). A browser User-Agent makes "
            "api.vxtwitter.com answer HTTP 403; the default avoids that." % DEFAULT_UA
        ),
    )
    parser.add_argument(
        "--timeout", type=float, default=20.0, metavar="SECONDS", help="per-request timeout (default: 20)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        metavar="N",
        help="retries per request on 429/5xx/network errors (default: 2)",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    stream = sys.stderr

    try:
        targets = [parse_target(raw) for raw in args.urls]
    except InputError as exc:
        print("%s: error: %s" % (PROG, exc), file=stream)
        return 2

    if args.output and len(targets) > 1:
        print(
            "%s: error: -o/--output can only be used with a single URL; use --outdir for several"
            % PROG,
            file=stream,
        )
        return 2

    client = HttpClient(
        debug=args.debug,
        timeout=args.timeout,
        max_retries=args.max_retries,
        user_agent=args.user_agent,
        stream=stream,
    )
    options = {"query_id": args.graphql_query_id, "auth_file": args.auth_file}
    try:
        providers = build_providers(args.provider, client, options)
    except InputError as exc:
        print("%s: error: %s" % (PROG, exc), file=stream)
        return 2

    exit_code = 0
    for target in targets:
        if args.debug:
            print(
                "[debug] resolving %s (id=%s) with provider=%s"
                % (target.display_url, target.status_id, args.provider),
                file=stream,
                flush=True,
            )
        try:
            document, _errors = fetch_document(
                target, providers, client, debug=args.debug, stream=stream
            )
        except NoProviderAvailable as exc:
            print("%s: error: could not retrieve %s" % (PROG, target.display_url), file=stream)
            print(str(exc), file=stream)
            exit_code = 1
            continue

        if args.json:
            payload = json.dumps(document_to_json(document), indent=2, ensure_ascii=False)
            text = payload + "\n"
        else:
            text = render_document(document)

        destination = write_output(
            text, args.output, args.outdir, default_filename(document)
        )
        if args.json and destination == "stdout":
            if len(targets) > 1:
                print("", file=stream)
        if destination != "stdout":
            print("%s -> %s" % (document.kind, destination), file=stream)
        if document.warnings and not args.debug:
            for warning in document.warnings:
                print("%s: note: %s" % (PROG, warning), file=stream)

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)
