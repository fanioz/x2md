# x2md

Convert an X (Twitter) **post**, **self-thread** or long-form **X Article** into clean Markdown.

Standard library only. No `pip install`, no API key, no account required.

Lives at `~/code/x2md`. All examples below assume you run them from that directory.

```console
$ cd ~/code/x2md
$ python3 x2md.py https://x.com/jack/status/20
post -> /current/dir/jack_20.md
```

---

## Install

Nothing to install. Python 3.9+ and the standard library are all that is needed.
The tool is a single self-contained file, `x2md.py`.

```console
$ python3 --version
Python 3.9.6
$ python3 x2md.py --help
```

Optional extras: none. Every retrieval strategy uses `urllib` from the standard library.

## Web app

A public web UI is included. Paste any X/Twitter URL or post ID and get the same clean Markdown output, ready to copy or download. Images and videos attached to the post (or thread) can be downloaded individually or as a single ZIP — original-resolution images and mp4 sources for videos/GIFs.

```
https://x2md.vercel.app
```

The web app uses the same Python core as the CLI, wrapped in a Vercel serverless function. No credentials, no history, and no analytics are collected.

### Develop locally

No Vercel CLI is required to work on the files, but you will need it to preview the serverless function locally:

```console
$ npm i -g vercel
$ vercel dev
```

The static frontend lives in `public/` and the API endpoint is `api/convert.py`.

## Usage

```
python3 x2md.py URL_OR_ID [URL_OR_ID ...] [-o FILE] [--outdir DIR] [--json]
                      [--provider {auto,fxtwitter,vxtwitter,syndication,graphql}]
                      [--debug] [--graphql-query-id ID] [--auth-file FILE]
                      [--user-agent UA] [--timeout SECONDS] [--max-retries N]
```

| Flag | Meaning |
| --- | --- |
| `-o, --output FILE` | Write to `FILE`. `-o -` writes Markdown to stdout. Single URL only. |
| `--outdir DIR` | Write `<handle>_<id>.md` into `DIR` (created if missing). Use with several URLs. |
| `--json` | Emit the normalised document as JSON instead of Markdown. |
| `--provider NAME` | Force one strategy instead of the `auto` chain. |
| `--debug` | Print the endpoint used and the raw HTTP status of every request to stderr. |
| `--graphql-query-id ID` | `TweetDetail` query id for the `graphql` provider. |
| `--auth-file FILE` | JSON file holding `auth_token` / `ct0` / `bearer_token`. |
| `--user-agent UA` | Override the User-Agent (see [Providers](#why-the-user-agent-matters)). |
| `--timeout`, `--max-retries` | Per-request timeout (default 20s) and retry budget (default 2). |

### Accepted inputs

All of these resolve to the same post:

```
https://x.com/XCreators/status/2072439205213421694
https://twitter.com/XCreators/status/2072439205213421694
https://mobile.x.com/XCreators/status/2072439205213421694?s=20&t=abc
https://www.x.com/XCreators/status/2072439205213421694/photo/1
https://twitter.com/i/web/status/2072439205213421694
https://twitter.com/XCreators/statuses/2072439205213421694
https://x.com/i/article/2072439205213421694
2072439205213421694
```

Supported hosts: `x.com`, `twitter.com`, `www.x.com`, `mobile.x.com`, `www.twitter.com`,
`mobile.twitter.com`. Query strings, fragments, trailing slashes, ports and a missing
`https://` scheme are all tolerated. Anything else is rejected with a clear error and
exit status `2`.

### Examples

```console
# single post to a named file
python3 x2md.py https://x.com/jack/status/20 -o jack.md

# a self-thread, reassembled into ONE ordered document
python3 x2md.py https://mobile.x.com/XCreators/status/2072439205213421694 --outdir out/

# a long-form X Article
python3 x2md.py https://x.com/XBusiness/status/2097390372670575039 -o article.md

# several URLs at once, plus normalised JSON
python3 x2md.py 20 2072439205213421694 --outdir out/ --json

# force a strategy and watch every request
python3 x2md.py https://x.com/jack/status/20 --provider syndication --debug -o -
```

### Output shape

YAML frontmatter, then the body:

```markdown
---
source: "https://x.com/jack/status/20"
tweet_id: "20"
author_name: "jack"
author_handle: "jack"
author_url: "https://x.com/jack"
posted_at: "2006-03-21T20:50:14+00:00"
kind: "post"
provider: "fxtwitter"
lang: "en"
likes: 308946
retweets: 124655
replies: 18044
quotes: 7191
bookmarks: 21632
---

# Post by jack (@jack)

just setting up my twttr

*2006-03-21T20:50:14+00:00 · <https://x.com/jack/status/20>*
```

`kind` is one of `post`, `thread`, `article`. Stat keys are omitted entirely when the
provider does not report them (never emitted as `null`).

Body rendering rules:

* Post text keeps its line breaks. A single newline becomes a Markdown hard break
  (trailing `\`); blank lines are left alone so paragraphs survive.
* **Threads** become one document with `## 1/5` … `## 5/5` sections in conversation order,
  each with its own permalink and timestamp.
* **Quoted posts** become a blockquote with their own author attribution; a quote inside
  a quote nests (`> > `).
* **Media** renders as Markdown links to the highest-resolution image (`?name=orig`) or
  the video thumbnail, with alt text when the post has it. Videos add a nested link to the
  best mp4. `pic.x.com/...` placeholder facets are stripped, since the media is rendered
  separately.
* **Polls** render as a list of options with percentages and vote counts.
* **Inline links** are preserved as `[label](target)`; a URL whose label is the URL itself
  becomes `<autolink>`.
* **Hashtags, mentions and cashtags** are left as plain readable text, deliberately not
  rewritten into links.
* **Articles** are rendered as real Markdown structure — `##`/`###` headings, paragraphs,
  bullet and numbered lists, blockquotes, fenced code, `---` dividers, inline links,
  images at full resolution, and embedded posts as linked blockquotes.
* All post, author and poll text is HTML-escaped, so pasted content cannot inject markup.

## Providers

`--provider` selects a retrieval strategy. The default `auto` tries them in order and
stops at the first success; each failure is reported with its own endpoint and HTTP status.

| Provider | Single post | Threads | Articles | Auth | Status in this build |
| --- | --- | --- | --- | --- | --- |
| `fxtwitter` | yes | **yes** | **yes** | none | **Verified live** — default and best source |
| `vxtwitter` | yes | no | no | none | **Verified live** (single posts) |
| `syndication` | yes | no | no | none | **Verified live** (single posts) |
| `graphql` | partly | partly | no | guest or optional | **Only verified up to the query-id boundary** — see limitations |
| `auto` | — | — | — | — | `fxtwitter` → `vxtwitter` → `syndication` → `graphql` |

* `fxtwitter` — `https://api.fxtwitter.com`. `GET /2/thread/{id}` returns the unrolled
  conversation, `GET /2/status/{id}` a single post; Articles arrive as a Draft.js document
  on the status object. This is the only no-auth source found that can enumerate threads
  and return full Article bodies.
* `vxtwitter` — `https://api.vxtwitter.com`. Single posts only. `GET /{handle|i}/status/{id}`.
* `syndication` — `https://cdn.syndication.twimg.com/tweet-result?id={id}&token={token}`.
  X's own public embed endpoint. Single posts only.
* `graphql` — `TweetDetail` against `api.x.com/graphql` with a guest token (or your cookies),
  for enumerating and reconstructing full threads.

### Why the User-Agent matters

The default User-Agent is `x2md/1.0`, **not** a browser string. Measured against the live
endpoints on 2026-09-18:

| User-Agent | fxtwitter | vxtwitter | syndication |
| --- | --- | --- | --- |
| Chrome browser string | 200 | **403** | 200 |
| `curl/8.7.1` | 200 | 200 | 200 |
| `x2md/1.0` | 200 | 200 | 200 |
| `python-urllib/3.9` | 200 | 200 | 200 |

A browser User-Agent gets `api.vxtwitter.com` to answer HTTP 403. Use `--user-agent` if you
need to change it.

### Rate limiting

Requests are strictly sequential: one request per provider per URL, at most four for the
whole `auto` chain. HTTP 429 and 5xx responses are retried up to `--max-retries` times
(default 2) with exponential backoff, honouring `Retry-After` and capping the wait at 15s.
There is no parallel request path anywhere in the tool.

## Auth (all optional)

The tool works with no credentials. Auth only affects the `graphql` provider, which is
otherwise unavailable.

| Variable | Meaning |
| --- | --- |
| `X2MD_BEARER_TOKEN` | Bearer token. Defaults to X's public web bearer constant. |
| `X2MD_AUTH_TOKEN` | Value of the `auth_token` cookie. |
| `X2MD_CT0` | Value of the `ct0` CSRF cookie. |
| `X2MD_GRAPHQL_QUERY_ID` | `TweetDetail` query id. Also settable via `--graphql-query-id`. |
| `X2MD_AUTH_FILE` | Path to a JSON file holding `auth_token`, `ct0`, `bearer_token`. |

Supply both `X2MD_AUTH_TOKEN` and `X2MD_CT0` to authenticate as your own account (they are
also sent as the `x-csrf-token` header). With neither, the provider activates an anonymous
guest token. A local auth file should be git-ignored — see `.gitignore`.

No credentials are ever written to disk or included in output.

---

# Known limitations / not verified

This section separates what was actually measured from what was not.

### Not verified

1. **A successful `graphql` `TweetDetail` fetch.** The guest-token handshake *was* verified
   live (`POST /1.1/guest/activate.json` → HTTP 200 with a `guest_token`), and a request with
   an unknown query id *was* verified live to fail with HTTP 404. What was **not** verified is
   a successful conversation fetch, because `TweetDetail` requires a `queryId` that X rotates
   on every web-client deploy. The logged-out JS bundle ships only entry/chunk manifests, and
   the route-specific chunk holding the query id is loaded dynamically, so it could not be
   extracted without executing the single-page app. **No query id is hardcoded**, precisely
   because an unverified constant would risk a silently wrong document. Supply a current id
   yourself; a stale one fails cleanly with HTTP 404 and a clear message.
2. **Thread assembly via `graphql`.** Consequence of (1): the TweetDetail normaliser is
   covered offline against a synthetic fixture, but no live thread was assembled through it.
   Thread assembly *is* verified live through `fxtwitter`.
3. **Poll rendering against real data.** No live poll post could be found (scanned many public
   timelines; several accounts returned zero polls in 20–50 recent posts each, and the mirror's
   search endpoint returns 404 without auth). The poll fixture is schema-derived from
   FxTwitter's published OpenAPI `poll` schema, not a live capture.
4. **Very large threads.** Only threads up to 5 posts were observed. Whether `fxtwitter`
   truncates long conversations (and whether `thread_complete` would then be wrong) was not
   measured.
5. **`vxtwitter` reliability.** It served a Cloudflare "Just a moment…" interstitial (HTTP 200
   with HTML, captured in the fixtures) on one attempt and HTTP 403 on another before the
   User-Agent fix; other attempts returned 200. It is treated as a best-effort fallback. The
   tool detects the interstitial and reports "expected JSON but received HTML" rather than
   crashing, but it cannot defeat a bot wall.
6. **Article `MARKDOWN` / `DIVIDER` / `TWEMOJI` entities.** `TWEET`, `MEDIA` and `LINK` were
   observed live and are rendered. `MARKDOWN`, `DIVIDER` and `TWEMOJI` appear in the schema
   (and `DIVIDER`/`TWEMOJI` in live articles) but are only covered by synthetic unit tests.
7. **Authenticated mode.** The cookie/bearer code path is implemented but never executed
   against a real account, since no credentials were available.
8. **`api.x.com/graphql` is undocumented and unversioned.** Everything about it is subject to
   change without notice.

### Behaviour that may surprise you

* **`thread_complete: false` is a real warning, not decoration.** When a provider cannot
  enumerate conversations but the post replies to its own author, the document is labelled
  incomplete and carries a warning rather than pretending to be a complete thread. When a
  provider has no thread support at all, a note is added saying the output is limited to the
  single requested post.
* **Any provider other than `fxtwitter` cannot expand threads or Articles.** `syndication`
  and `vxtwitter` return a single post; a requested thread root will look like a plain post.
* **The syndication `token` parameter is not validated.** Measured 2026-09-18: any non-empty
  value (`a`, `deadbeef`) returns the post, and an empty value returns an empty body. The token
  is still computed properly so the request stays correct if validation is reintroduced.
* **Facet offsets are codepoint-based, not UTF-16.** FxTwitter's OpenAPI document describes
  facet `indices` as "UTF-16 indices", but live payloads index by codepoint — verified against
  a post containing the astral character U+1D54F, where codepoint slicing selects exactly the
  expected substring and UTF-16 slicing is off by one. The code follows the observed behaviour
  (`FACET_INDICES_ARE_UTF16 = False`).
* **`entityMap` is not stored in key order.** In live Article payloads the `key` values are a
  permutation of the array positions. Indexing that array by position silently pairs the wrong
  URL with a link label; entities are looked up by their `key` field instead. This is guarded
  by a regression test.
* **Some media facets have out-of-range indices.** Observed values such as `[127, 150]` against
  a 126-character body. Ranges are bounds-checked and out-of-range facets are dropped.
* **Article link labels can look mismatched in the source data.** In one live Article, an entity
  labelled "Terms of Service" carried an appeals-form URL. Labels and URLs are now read from the
  same entity, so this reflects the upstream payload, not the parser. It was not root-caused.
* **`vxtwitter`'s `date_epoch` is computed locally**, so `posted_at` comes from the provider's
  own `date` field where available.
* **Media links point at images and thumbnails, not video files.** For a video the primary link
  is the poster thumbnail (as specified); the mp4 is a nested secondary link.
* **Bold/italic facets are not rendered.** `raw_text.facets` can carry `bold` ranges; they are
  left as plain text.

### Legal / etiquette

This tool retrieves public posts through publicly reachable endpoints. Respect the terms of
service of X and of any mirror you use, keep request volume low (the tool is sequential and
retries conservatively by design), and do not use it to bulk-harvest content.

---

## Tests

193 tests, entirely offline against recorded fixtures — no network access at all.

```console
$ python3 -m unittest discover -s tests
----------------------------------------------------------------------
Ran 193 tests in 0.572s

OK
```

Coverage: URL/ID parsing for every accepted and rejected form; the facet, media, poll and
quote converters; YAML frontmatter escaping of adversarial input (quotes, colons, newlines,
`<script>`, YAML document markers, U+2028); thread ordering, numbering and degradation;
Article Draft.js block and entity rendering including the `entityMap` permutation regression;
provider normalisation and error reporting; bounded 429 retry behaviour; and end-to-end CLI
runs with a stubbed HTTP layer.

To prove the suite never touches the network, run it with sockets blocked — any real
connection attempt raises immediately:

```console
$ X2MD_TEST_BLOCK_NETWORK=1 python3 -m unittest discover -s tests
----------------------------------------------------------------------
Ran 193 tests in 0.528s

OK
```

Fixtures live in `tests/fixtures/`; `fixtures/README.md` records the provenance of each
one and marks the two that are synthetic or schema-derived rather than captured live.
