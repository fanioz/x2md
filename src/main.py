#!/usr/bin/env python3
"""Apify Actor entry point: scrape X/Twitter posts, threads, and Articles.

Reads input via ``Actor.get_input``, processes each URL through the
stdlib-only mapping layer in ``actor_lib`` (which reuses ``x2md.py``
read-only), pushes one dataset item per URL via ``Actor.push_data`` with a
``dataset-item`` Pay-Per-Event charge, and uploads media files plus a ZIP
bundle to the key-value store via ``Actor.set_value``.

Proxy: every HTTP request (provider JSON + media bytes) goes through the
Apify Proxy URL from ``Actor.create_proxy_configuration`` (fed the user's
``proxyConfiguration`` input) when one is available; without platform
proxy env vars the run proceeds direct and logs
a warning. ``x2md.HttpClient`` has no proxy knob, so this module installs
a process-global ``urllib`` opener carrying a ``ProxyHandler`` — the only
code path that performs HTTP in this process is urllib, so nothing else is
affected.

Logging: all operational logging goes through ``Actor.log`` (which censors
``APIFY_TOKEN`` and, via ``_CENSORED_PATTERNS``, our own credential names).
``x2md.HttpClient`` debug logging stays off; failures are reported per item.
"""

import asyncio
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apify import Actor

import actor_lib
import x2md

CHARGE_EVENT_DATASET_ITEM = "dataset-item"

# Each entry must be a real env-var/cookie name: the redaction regex demands a
# separator right after the pattern, so a bare "X2MD_" prefix would never match
# (and X2MD_GRAPHQL_QUERY_ID=... would leak its value into logs).
_CENSORED_PATTERNS = ("auth_token", "ct0", "bearer_token", "X2MD_GRAPHQL_QUERY_ID")


def _redact(text):
    """Mask known credential names and their values in log messages."""
    for pattern in _CENSORED_PATTERNS:
        text = re.sub(
            r"(?i)(%s[\"'\s:=]+)([^\s\"',}]+)" % re.escape(pattern),
            r"\1***",
            str(text),
        )
    return text


async def _proxy_url(raw_input):
    """Return an Apify Proxy URL string, or None when unavailable."""
    try:
        # Keyword-only on the SDK side: without actor_proxy_input the user's
        # proxyConfiguration input field would be silently ignored.
        config = await Actor.create_proxy_configuration(
            actor_proxy_input=raw_input.get("proxyConfiguration")
        )
    except Exception as exc:
        Actor.log.warning("Proxy unavailable, continuing without proxy: %s", _redact(exc))
        return None
    if config is None:
        Actor.log.warning("Proxy unavailable, continuing without proxy.")
        return None
    try:
        url = await config.new_url()
    except Exception as exc:
        Actor.log.warning("Proxy unavailable, continuing without proxy: %s", _redact(exc))
        return None
    return url


def _install_proxy_opener(proxy_url):
    """Route all urllib HTTP/HTTPS traffic through the proxy URL."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )
    urllib.request.install_opener(opener)


def _download_bytes(url, timeout=30):
    """Fetch a media asset using the process's configured urllib opener."""
    request = urllib.request.Request(url, headers={"User-Agent": "x2md-actor/%s" % x2md.__version__})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type")


def _record_content_type(resp_type, key):
    """Prefer the response Content-Type; fall back to the extension default."""
    content_type = (resp_type or "").split(";", 1)[0].strip()
    if not content_type:
        content_type = "video/mp4" if key.endswith(".mp4") else "image/jpeg"
    return content_type


async def _upload_media(plan, doc_id):
    """Download each planned asset and store it; return uploaded keys."""
    uploaded = []
    for entry in plan:
        try:
            data, resp_type = await asyncio.to_thread(_download_bytes, entry["download_url"])
        except Exception as exc:
            Actor.log.warning(
                "Media download failed for %s (item %s): %s",
                _redact(entry["key"]),
                doc_id,
                _redact(exc),
            )
            continue
        await Actor.set_value(
            entry["key"], data, content_type=_record_content_type(resp_type, entry["key"])
        )
        uploaded.append(entry["key"])
    return uploaded


async def _upload_zip(keys, run_ts):
    """Bundle already-uploaded media into a ZIP in the key-value store."""
    zip_key = "zip_run_%d.zip" % run_ts
    # Build on disk: buffering the whole archive in a BytesIO (and copying it
    # again in getvalue) would double the peak RAM of the largest media set.
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = pathlib.Path(tmp_dir) / zip_key
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for key in keys:
                record = await Actor.get_value(key)
                if record is None:
                    Actor.log.warning("Skipping missing media file in ZIP: %s", _redact(key))
                    continue
                data = record if isinstance(record, (bytes, bytearray)) else bytes(record)
                archive.writestr(key.split("_", 1)[1], data)
        await Actor.set_value(zip_key, zip_path.read_bytes(), content_type="application/zip")
    return zip_key


async def main():
    """Process Actor input and publish dataset items and requested media."""
    async with Actor:
        raw_input = await Actor.get_input() or {}
        try:
            cleaned = actor_lib.validate_input(raw_input)
        except actor_lib.ActorInputError as exc:
            Actor.log.error("Invalid Actor input: %s", exc)
            raise ValueError(str(exc)) from exc

        # Optional GraphQL auth passes straight through to x2md.py, which
        # reads X2MD_GRAPHQL_QUERY_ID / X2MD_AUTH_TOKEN / X2MD_CT0 /
        # X2MD_BEARER_TOKEN from the environment. Set them as secret
        # environment variables in the Apify Console; never in input.
        proxy_url = await _proxy_url(raw_input)
        if proxy_url:
            _install_proxy_opener(proxy_url)
            Actor.log.info("Using Apify Proxy for all HTTP requests.")

        run_ts = int(time.time() * 1000)
        urls = cleaned["startUrls"][: cleaned["maxItems"]]
        Actor.log.info("Processing %d URL(s) with provider '%s'.", len(urls), cleaned["provider"])

        all_media_keys = []
        for url in urls:
            item = await asyncio.to_thread(actor_lib.fetch_one, url, cleaned, run_ts)
            if "error" in item:
                Actor.log.warning("Skipping invalid URL %r: %s", url, item["error"])
                await Actor.push_data(item)
                continue
            if "failedProviders" in item:
                Actor.log.warning(
                    "All providers failed for %s: %s",
                    url,
                    _redact(item["failedProviders"]),
                )
                await Actor.push_data(item)
                continue

            media_plan = _plan_from_item(item)
            uploaded = []
            if media_plan:
                uploaded = await _upload_media(media_plan, item["id"])
                # Drop fileKeys that failed to download so the dataset stays honest.
                ok = set(uploaded)
                for ref in actor_lib.iter_file_refs(item):
                    if ref.get("fileKey") not in ok:
                        ref["fileKey"] = None
                all_media_keys.extend(uploaded)
            if item.get("warnings"):
                Actor.log.warning("Warnings for %s: %s", url, "; ".join(item["warnings"]))
            await Actor.push_data(item, CHARGE_EVENT_DATASET_ITEM)
            Actor.log.info("Pushed dataset item for %s via %s.", url, item.get("provider"))

        if cleaned["downloadMedia"].get("zip") and all_media_keys:
            zip_key = await _upload_zip(all_media_keys, run_ts)
            Actor.log.info("Uploaded media bundle %s (%d files).", zip_key, len(all_media_keys))

        Actor.log.info("Done: %d item(s), %d media file(s).", len(urls), len(all_media_keys))


def _plan_from_item(item):
    """Rebuild download entries for media refs that carry a fileKey."""
    return [
        {"key": ref["fileKey"], "download_url": ref["url"]}
        for ref in actor_lib.iter_file_refs(item)
        if ref.get("url")
    ]


if __name__ == "__main__":
    asyncio.run(main())
