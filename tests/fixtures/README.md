# Test fixtures

All tests run **offline** against these recorded payloads. Nothing in the test suite
touches the network.

## Provenance

| File | Source | Notes |
| --- | --- | --- |
| `fxtwitter_v2_status_simple.json` | live capture — `GET https://api.fxtwitter.com/2/status/20` | jack's first post, 2006 |
| `fxtwitter_v2_thread5.json` | live capture — `GET https://api.fxtwitter.com/2/thread/2072439205213421694` | real 5-post self-thread |
| `fxtwitter_v2_article.json` | live capture — `GET https://api.fxtwitter.com/2/status/2097390372670575039` | long-form Article, 42 blocks, headings + lists + embedded posts |
| `fxtwitter_v2_article_media.json` | live capture — `GET https://api.fxtwitter.com/2/status/2085835082166653393` | Article with 6 `MEDIA` entities resolving to `ApiImage` |
| `fxtwitter_v2_quote.json` | live capture — `GET https://api.fxtwitter.com/2/status/2099922471272976442` | quoted-post rendering |
| `fxtwitter_v2_photos.json` | live capture — `GET https://api.fxtwitter.com/2/status/2088006016721940988` | still image media |
| `fxtwitter_v2_video.json` | live capture — `GET https://api.fxtwitter.com/2/status/2095249317875622255` | video media, multiple mp4 renditions |
| `vxtwitter_status_simple.json` | live capture — `GET https://api.vxtwitter.com/i/status/20` | handle-less mirror path |
| `vxtwitter_status_video.json` | live capture — `GET https://api.vxtwitter.com/i/status/2095249317875622255` | `media_extended` shape |
| `vxtwitter_cloudflare_challenge.html` | live capture (trimmed) — Cloudflare interstitial returned by vxtwitter | real observed error mode: HTTP 200 with HTML, not JSON |
| `syndication_status_simple.json` | live capture — `GET https://cdn.syndication.twimg.com/tweet-result?id=20&token=t` | |
| `syndication_quote.json` | live capture — `GET https://cdn.syndication.twimg.com/tweet-result?id=2099922471272976442&token=t` | quoted post + video + `mediaDetails` |
| `fxtwitter_v2_poll.json` | **schema-derived, NOT a live capture** | no live poll post could be located; `poll` object matches the schema published in `https://api.fxtwitter.com/2/openapi.json` |
| `fxtwitter_v2_adversarial.json` | **synthetic** | adversarial author name / body text for YAML + HTML injection tests |

The two schema-derived/synthetic fixtures are labelled as such in their own filenames
and in this table so that no test claims more provenance than it has.
