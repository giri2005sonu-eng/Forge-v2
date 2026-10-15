"""Seller-link discovery for a catalog part, powered by TinyFish.

Stage 1  find_sources():  TinyFish *Search* (several query variants) -> at least `target`
                          distinct selling links, one per store first, ranked Indian
                          electronics vendors first.
Stage 2  check_prices():  TinyFish *Fetch* (live page text) -> Gemini extraction -> the same
                          quote-verification used elsewhere (core.live). A price is only shown
                          when it is backed by a verbatim quote from the page.

Results are cached in data/sourcing_cache.json so the demo is fast the second time.
Links that TinyFish could not supply are padded with clearly-labelled vendor search
pages ("fallback") so the UI never silently mixes real search hits with generic links.
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote_plus

from core.config import DATA_DIR
from .live import SKIP_DOMAINS, domain_of, extract_from_page
from core.schemas import Part, now_iso
from .tinyfish import TinyFishClient

CACHE_NAME = "sourcing_cache.json"
_lock = threading.Lock()

# Not shops: docs, forums, wikis, video, blogs. Dropped from the results.
NON_STORE_DOMAINS = SKIP_DOMAINS + (
    "wikipedia.org", "github.com", "instructables.com", "hackster.io", "stackexchange.com",
    "stackoverflow.com", "medium.com", "arduino.cc", "espressif.com", "twitter.com", "x.com",
    "linkedin.com", "scribd.com", "slideshare.net", "researchgate.net", "arduino.stackexchange.com",
)

# Fallback search pages (only used to pad up to the target and labelled as such in the UI).
FALLBACK_SEARCH = {
    "robu.in": "https://robu.in/?s={q}&post_type=product",
    "robocraze.com": "https://robocraze.com/search?q={q}",
    "quartzcomponents.com": "https://quartzcomponents.com/search?q={q}",
    "amazon.in": "https://www.amazon.in/s?k={q}",
    "electronicscomp.com": "https://www.electronicscomp.com/catalogsearch/result/?q={q}",
    "thinkrobotics.com": "https://thinkrobotics.com/search?q={q}",
    "evelta.com": "https://evelta.com/search/?q={q}",
}


def core_name(name: str) -> str:
    """'Arduino Uno R3 (compatible)' -> 'Arduino Uno R3'."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def query_variants(part: Part) -> list[str]:
    core = core_name(part.name)
    out = [part.search_query or f"{part.name} buy India price",
           f"{core} buy online India",
           f"{core} price in India robu.in robocraze amazon.in",
           f"buy {core} online"]
    seen, uniq = set(), []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq


def _is_store(url: str) -> bool:
    d = domain_of(url)
    return bool(d) and not any(d == s or d.endswith("." + s) for s in NON_STORE_DOMAINS)


def _rank_key(url: str, allowed: list[str]):
    d = domain_of(url)
    for i, a in enumerate(allowed):
        if d == a or d.endswith("." + a):
            return (0, i)
    return (1, 0)


def pick_links(results: list[dict], allowed: list[str], target: int) -> list[dict]:
    """Dedupe + rank. Pass 1: one link per store; pass 2: extra links from the same stores."""
    seen_urls: set[str] = set()
    cands = []
    for r in results:
        url = r.get("url")
        if not isinstance(url, str) or not url.startswith("http") or url in seen_urls or not _is_store(url):
            continue
        seen_urls.add(url)
        cands.append(r)
    cands.sort(key=lambda r: _rank_key(r["url"], allowed))  # stable: keeps TinyFish order inside a tier
    first, rest, seen_dom = [], [], set()
    for r in cands:
        d = domain_of(r["url"])
        (rest if d in seen_dom else first).append(r)
        seen_dom.add(d)
    return (first + rest)[:min(max(target, len(first)), 8)]  # all distinct stores found, capped at 8


def _link_row(r: dict, query: str) -> dict:
    url = r["url"]
    snippet = r.get("snippet") or r.get("description") or ""
    return {"url": url, "domain": domain_of(url), "vendor": r.get("site_name") or domain_of(url),
            "title": (r.get("title") or "").strip()[:160], "snippet": str(snippet).strip()[:220],
            "source": "tinyfish_search", "query": query}


def fallback_rows(part: Part, have_domains: set[str], need: int) -> list[dict]:
    q = quote_plus(core_name(part.name))
    rows = []
    for dom, pattern in FALLBACK_SEARCH.items():
        if len(rows) >= need:
            break
        if dom in have_domains:
            continue
        rows.append({"url": pattern.format(q=q), "domain": dom, "vendor": dom,
                     "title": f"Search “{core_name(part.name)}” on {dom}", "snippet": "",
                     "source": "fallback_search_page", "query": ""})
    return rows


# ------------------------------------------------------------------ cache
def _cache_path(data_dir: Path) -> Path:
    return data_dir / CACHE_NAME


def _read_cache(data_dir: Path) -> dict:
    p = _cache_path(data_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(data_dir: Path, cache: dict) -> None:
    _cache_path(data_dir).write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_cache(data_dir: Path = DATA_DIR) -> None:
    p = _cache_path(data_dir)
    if p.exists():
        p.unlink()


# ------------------------------------------------------------------ stage 1: links
def find_sources(part: Part, tf: TinyFishClient, allowed_domains: list[str], target: int = 5,
                 max_queries: int = 4, refresh: bool = False, data_dir: Path = DATA_DIR) -> dict:
    with _lock:
        cache = _read_cache(data_dir)
    hit = cache.get(part.id)
    if hit and not refresh and sum(1 for l in hit["links"] if l["source"] == "tinyfish_search") >= target:
        return {**hit, "cached": True}

    pool: list[dict] = []
    queries_run: list[str] = []
    problems: list[str] = []
    picked: list[dict] = []
    for q in query_variants(part)[:max_queries]:
        try:
            results = tf.search(q)
        except Exception as e:  # one failed query must not lose what earlier queries found
            problems.append(f"search '{q}': {e}")
            continue
        queries_run.append(q)
        for r in results:
            if isinstance(r, dict):
                r = dict(r)
                r["_q"] = q
                pool.append(r)
        picked = pick_links(pool, allowed_domains, target)
        if len({domain_of(r["url"]) for r in picked}) >= target:
            break

    links = [_link_row(r, r.get("_q", "")) for r in picked]
    tinyfish_count = len(links)
    if tinyfish_count < target:
        links += fallback_rows(part, {l["domain"] for l in links}, target - tinyfish_count)
    if tinyfish_count == 0 and problems:
        raise RuntimeError(problems[0])
    for i, l in enumerate(links, 1):
        l["rank"] = i

    out = {"part_id": part.id, "part_name": part.name, "fetched_at": now_iso(), "links": links,
           "tinyfish_count": tinyfish_count, "fallback_count": len(links) - tinyfish_count,
           "queries": queries_run, "problems": problems, "prices": (hit or {}).get("prices", {}) if not refresh else {}}
    with _lock:
        cache = _read_cache(data_dir)
        cache[part.id] = out
        _write_cache(data_dir, cache)
    return {**out, "cached": False}


# ------------------------------------------------------------------ stage 2: prices
def check_prices(part: Part, urls: list[str], tf: TinyFishClient, llm_json: Callable[[str, str], dict],
                 spec_defs: dict, data_dir: Path = DATA_DIR, workers: int = 3) -> dict:
    """Live-fetch each URL with TinyFish and extract a quote-verified price / stock with Gemini."""
    urls = [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith("http")][:10]
    result: dict[str, dict] = {u: {"price": None, "in_stock": None, "matches": None, "quote": None,
                                   "product": None, "error": None} for u in urls}
    if not urls:
        return {"prices": result}
    pages, errs = tf.fetch(urls)
    by_url = {}
    for p in pages:
        for key in (p.get("url"), p.get("final_url")):
            if key:
                by_url[key] = p
    for e in errs:
        if e.get("url") in result:
            result[e["url"]]["error"] = str(e.get("error") or "fetch failed")[:120]

    def work(u: str):
        pg = by_url.get(u)
        if not pg or not isinstance(pg.get("text"), str) or not pg["text"].strip():
            result[u]["error"] = result[u]["error"] or "No readable page text (may need JS or login)"
            return
        try:
            ex = extract_from_page(llm_json, part.category, spec_defs, pg["text"], requested_name=part.name)
        except Exception as e:
            result[u]["error"] = f"Extraction failed: {str(e)[:100]}"
            return
        r = result[u]
        r["product"], r["matches"] = ex.product_name, ex.matches
        if ex.price:
            r["price"], r["quote"] = ex.price[0], ex.price[1][:200]
        if ex.stock:
            r["in_stock"] = ex.stock[0]
        if not ex.price and not r["error"]:
            r["error"] = "No verifiable price on page"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, urls))

    stamp = now_iso()
    with _lock:
        cache = _read_cache(data_dir)
        if part.id in cache:
            cache[part.id].setdefault("prices", {}).update({u: {**v, "checked_at": stamp} for u, v in result.items()})
            _write_cache(data_dir, cache)
    return {"prices": result, "checked_at": stamp}
