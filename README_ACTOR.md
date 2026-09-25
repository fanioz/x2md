# x2md Twitter Post Scraper

Turn X/Twitter posts, self-threads, and X Articles into structured dataset items plus clean Markdown. Optionally download original-resolution images, videos, and GIFs to your run's key-value store.

## What it does

- **Posts, threads, and Articles** – pass one or more post URLs or bare status IDs. The Actor returns one dataset item per URL.
- **Structured + Markdown** – every item contains the post text, author, engagement stats, poll/quote/article metadata, and a Markdown body.
- **Thread mode** – for self-threads you can choose flat, nested, or both output shapes.
- **Optional media downloads** – original-resolution images, best mp4 sources, and GIFs can be uploaded to the key-value store, with an optional ZIP bundle.
- **Provider fallback** – tries FxTwitter first, then VxTwitter, syndication, and an optional GraphQL provider.

## Pricing

- **Pay-Per-Event**: `$0.001` per dataset item.
- **Free tier**: `100 dataset items / month`.
- Invalid URLs and total provider failures are reported as error rows in the dataset free of charge — only successful dataset items trigger the charge.
- Media downloads and ZIP bundling use your Apify key-value store; storage is billed separately by Apify.

## Input

Example input:

```json
{
  "startUrls": [
    { "url": "https://x.com/jack/status/20" },
    { "url": "https://x.com/elonmusk/status/1770012345678900000" }
  ],
  "maxItems": 10,
  "provider": "auto",
  "downloadMedia": {
    "images": false,
    "videos": false,
    "gifs": false,
    "zip": false
  },
  "outputFormat": "both"
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `startUrls` | yes | — | Array of post/Article URLs or bare numeric IDs. |
| `maxItems` | no | 10 | URLs to process per run; maximum 50, higher values are rejected. |
| `provider` | no | `"auto"` | `"auto"`, `"fxtwitter"`, `"vxtwitter"`, `"syndication"`, or `"graphql"`. |
| `downloadMedia` | no | all `false` | Toggle images/videos/gifs and the optional ZIP bundle. |
| `outputFormat` | no | `"both"` | `"flat"`, `"nested"`, or `"both"` (threads only). |

## Output

Each row in the default dataset is one item with these top-level fields:

```json
{
  "id": "20",
  "url": "https://x.com/jack/status/20",
  "kind": "post",
  "author": { "handle": "jack", "name": "jack", "avatarUrl": "" },
  "markdown": "# ...",
  "threadComplete": true,
  "warnings": [],
  "provider": "fxtwitter",
  "providerErrors": [],
  "posts": [...],
  "thread": { "posts": [...], "complete": true }
}
```

Post objects include:

- `id`, `url`, `text`, `createdAt`, `lang`
- `stats`: `likes`, `retweets`, `replies`, `views`, `quotes`, `bookmarks`
- `poll`, `quote`, `article` (when present)
- `media`: array with `type`, `url`, `fileKey` (when downloaded), `altText`
- `threadPosition`, `threadComplete`, `conversationId` (threads)

Error rows are different. A URL that fails validation produces:

```json
{ "url": "https://x.com/not-a-post", "error": "..." }
```

A URL where every provider failed produces:

```json
{ "id": "20", "url": "https://x.com/jack/status/20", "failedProviders": [ { "provider": "fxtwitter", "message": "...", "url": "...", "status": 503 } ] }
```

## Optional GraphQL provider

If FxTwitter and VxTwitter are rate-limited or missing data, you can enable the GraphQL fallback by setting these environment variables in the Apify Console:

- `X2MD_GRAPHQL_QUERY_ID`
- `X2MD_AUTH_TOKEN`
- `X2MD_CT0`
- `X2MD_BEARER_TOKEN`

Set them as secret environment variables in the Apify Console (never in the run input); the Actor censors their values from its logs.

## Proxy

Residential proxy is strongly recommended. The Actor uses Apify Proxy when available; otherwise it logs a warning and runs direct.

## Links

- Source: https://github.com/fanioz/x2md
- Changelog: https://github.com/fanioz/x2md/blob/main/CHANGELOG.md
