# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-22

### Added

- Initial Apify Actor release: scrape X/Twitter posts, self-threads, and Articles.
- Provider fallback: fxtwitter → vxtwitter → syndication → optional graphql.
- Structured dataset output with Markdown body, media refs, polls, quotes, and articles metadata.
- Optional media downloads (images, videos, GIFs) and ZIP bundle to key-value store.
- `maxItems` clamped to 50 to match the 128 MB platform memory budget.
- `threadComplete` flag and `thread_incomplete` warning for partial threads.
- Pay-Per-Event pricing at $0.001 per dataset item with a 100-item/month free tier.
- Fully pinned `requirements.txt` and hardened Dockerfile to avoid floating transitive dependency breaks.
- GitHub Actions CI for Python 3.9/3.11 and Docker build.
- Automated `apify push` on pushes to `main`.

[Unreleased]: https://github.com/fanioz/x2md/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fanioz/x2md/releases/tag/v0.1.0
