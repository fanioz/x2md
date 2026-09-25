# Maintenance guide for the x2md Apify Actor

## Rotating secrets

### GraphQL query id

X rotates the `TweetDetail` query id on every web deploy. When the public
GraphQL provider starts failing consistently:

1. Open a Twitter/X post in a browser with the developer network tab.
2. Find the `TweetDetail` GraphQL request and copy the query id from the URL.
3. Update the `X2MD_GRAPHQL_QUERY_ID` environment variable in the Apify Console.

Rotate at least once per quarter or immediately after X deploys a major change.

### Authentication cookies (`X2MD_AUTH_TOKEN`, `X2MD_CT0`)

These are session cookies. If you use the GraphQL provider with authentication:

- Rotate when the Actor starts receiving 401/403 responses.
- Rotate when you change your X password or log out of sessions.
- Never commit them to the repository; always use Apify Console secrets.

### Bearer token (`X2MD_BEARER_TOKEN`)

The public bearer token rarely changes. If it does, update `X2MD_BEARER_TOKEN`
in the Apify Console. The fallback default in `x2md.py` should be updated in the
same PR.

## Monitoring

Watch these indicators after each `apify push`:

- Average run memory stays below 128 MB.
- Dataset item charge events match the number of successfully scraped URLs (invalid URLs and all-provider failures are pushed as error rows without a charge).
- `providerErrors` rate is low; spikes indicate a provider outage or IP block.
- `thread_incomplete` warnings spike when FxTwitter thread endpoints degrade.

## Monthly health checks

Once a month, run a small fixture input against the Actor to confirm FxTwitter
is still returning threads correctly. The fixture contains two URLs: a single
post (basic smoke) and a known public 5-post self-thread (`XCreators` status
`2072439205213421694`), which is what exercises FxTwitter's multi-post thread
enumeration:

```bash
apify run -p --input-file tests/fixtures/sample-input.json
```

If the run returns `thread_incomplete` for that known public thread that
previously resolved fully, FxTwitter's thread endpoint may have changed and the
GraphQL fallback or provider order may need review.

## Common issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `from apify import Actor` fails at container start | Floating transitive dependency broke the SDK install | Pin dependencies; rebuild Docker image; check `requirements.txt` |
| Runs exit quickly with empty dataset | All providers failed or input was invalid | Check `providerErrors` and input schema |
| Media files missing | Download toggles off or provider has no media | Verify `downloadMedia` and check the key-value store |
| Thread only returns first post | Provider returned a single self-reply; thread is incomplete | Use `threadComplete`/`thread_incomplete` to detect; retry with GraphQL |

## Release checklist

1. Update `CHANGELOG.md` under `[Unreleased]`.
2. Bump `VERSION` and `.actor/actor.json` version.
3. Open a PR; wait for CI and Docker build to pass.
4. Merge to `main`; the `apify.yml` workflow pushes the new version.
5. The `release.yml` workflow creates a git tag and GitHub Release.
