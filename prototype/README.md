# PROTOTYPE — Actor sample run (throwaway, ticket #7)

Answers: "what does one Actor run look like end to end?"

- `actor_sample_run.py` — offline, fixture-backed (`tests/fixtures/*.json`).
  Replays 3 cases through the real `x2md.py` pipeline
  (`parse_target` → `fetch_document` → `render_document`), then maps each
  `Document` onto the dataset-item contract from ticket #5 and the provider
  strategy from ticket #6.
- `sample-run/` — generated output: `INPUT.json`, `dataset.json`,
  one `.md` per case, `kv-store.txt` (KV file keys the Actor would upload).

Run: `python3 prototype/actor_sample_run.py` (no network, no `pip install`).

Findings (kept on the issue, not here):
- Flat+nested output, Markdown body, media refs with `fileKey`,
  `provider`/`providerErrors`, and `warnings` all render as specced.
- Total-failure path (`NoProviderAvailable`) yields a `failedProviders`
  chain per provider strategy.
- Fixture gaps (not prototype bugs): `avatarUrl` always empty
  (fixtures carry `avatar_url` but no actor-facing field was specced),
  `altText` empty, thread-5 fixture video fileKey indexes per post.
