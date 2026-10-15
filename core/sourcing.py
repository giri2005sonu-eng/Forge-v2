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

from .config import DATA_DIR
from .live import SKIP_DOMAINS, _norm, domain_of, extract_from_page, quote_in_text
from .schemas import Evidence, Part, Spec, now_iso
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



# ------------------------------------------------------------------ rule-based page reading (no LLM, no quota)
_PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]{1,9}(?:\.\d{1,2})?)", re.I)
_NOT_A_PRICE = re.compile(r"(?:over|above|between|minimum|min\.?|orders?|shipping|free|cashback|save|saving|off|emi|"
                          r"per month|/month|cod|coupon|discount|upto|up to|worth|from|\d\s*(?:to|-|–|and))\W*$", re.I)
_PRICE_WORDS = re.compile(r"(?:price|sale|offer|now|our|buy for|only for|at|special)\W*$", re.I)
_MRP_WORDS = re.compile(r"(?:mrp|m\.r\.p|regular|list price|was)\W*$", re.I)


def _clean_quote(text: str, a: int, b: int) -> str:
    """Verbatim slice of the page, trimmed so it neither starts nor ends in the middle of a word."""
    if a > 0 and text[a - 1].isalnum():
        a = (text.find(" ", a) + 1) or a
    if b < len(text) and text[b].isalnum():
        b = text.rfind(" ", a, b) if text.rfind(" ", a, b) > a else b
    return text[a:b].replace("\n", " ").strip()


def rule_price(text: str, lo: float = 10.0, hi: float = 200000.0) -> Optional[tuple[float, str]]:
    """Best price on the page as (value, verbatim quote). Skips shipping thresholds, EMI, MRP, etc."""
    best = None  # (score, position, value, quote)
    for m in _PRICE_RE.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if not (lo <= v <= hi):
            continue
        before = text[max(0, m.start() - 28):m.start()]
        if _NOT_A_PRICE.search(before):
            continue
        score = 2 if _PRICE_WORDS.search(before) else 0
        if _MRP_WORDS.search(before):
            score -= 2
        quote = _clean_quote(text, max(0, m.start() - 24), min(len(text), m.end() + 12))
        cand = (score, -m.start(), v, quote)
        if best is None or cand[:2] > best[:2]:
            best = cand
    return (best[2], best[3]) if best else None


def rule_stock(text: str) -> Optional[tuple[bool, str]]:
    for pat, val in ((r"out of stock|sold out|currently unavailable|notify me when", False),
                     (r"\bin stock\b|add to cart|buy now|available", True)):
        m = re.search(pat, text, re.I)
        if m:
            return val, _clean_quote(text, max(0, m.start() - 10), min(len(text), m.end() + 10))
    return None


def variant_matches(part: Part, text: str) -> bool:
    low = text.lower()
    toks = [t for t in re.findall(r"[a-z0-9]{2,}", core_name(part.name).lower())]
    if toks and sum(t in low for t in toks) / len(toks) < 0.6:
        return False
    if "compatible" in part.name.lower() and re.search(r"\b(original|genuine|official)\b", low) and "compatible" not in low:
        return False
    return True


def friendly_error(msg: str) -> str:
    m = (msg or "").lower()
    if "429" in m or "resource_exhausted" in m or "quota" in m:
        return "Gemini quota reached (429); rule-based reading found no price"
    if "bot_blocked" in m:
        return "Site blocked automated access"
    if "empty_content" in m:
        return "Page returned no content"
    return (msg or "Unverified")[:70]


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
_llm_lock = threading.Lock()  # Gemini backup is called one page at a time to respect rate limits


def check_prices(part: Part, urls: list[str], tf: TinyFishClient, llm_json: Optional[Callable[[str, str], dict]],
                 spec_defs: dict, data_dir: Path = DATA_DIR, workers: int = 4) -> dict:
    """TinyFish Fetch each URL. Gemini reads price/stock from the page; if Gemini is unavailable or finds
    nothing, rules read the page text instead. Every value carries a verbatim page quote."""
    urls = [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith("http")][:10]
    result: dict[str, dict] = {u: {"price": None, "in_stock": None, "matches": None, "quote": None,
                                   "product": None, "error": None, "method": None} for u in urls}
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
            result[e["url"]]["error"] = friendly_error(str(e.get("error") or "fetch failed"))

    def work(u: str):
        r = result[u]
        pg = by_url.get(u)
        text = pg.get("text") if pg else None
        if not isinstance(text, str) or not text.strip():
            r["error"] = r["error"] or "Page returned no readable text"
            return
        r["error"] = None
        r["matches"] = variant_matches(part, text)
        # 1) Gemini reads the page first (as before), one page at a time, quote-checked against the page text
        if llm_json is not None:
            try:
                with _llm_lock:
                    ex = extract_from_page(llm_json, part.category, spec_defs, text, requested_name=part.name)
                r["product"] = ex.product_name
                if ex.matches is not None:
                    r["matches"] = ex.matches and r["matches"]
                if ex.price:
                    r["price"], r["quote"], r["method"] = ex.price[0], ex.price[1][:200], "Gemini + quote check"
            except Exception as e:
                r["error"] = friendly_error(str(e))
        # 2) Backup: if Gemini is unavailable (quota/429/no key) or found nothing, read the page text by rules
        if r["price"] is None:
            hit = rule_price(text)
            if hit and quote_in_text(hit[1], _norm(text)):
                r["price"], r["quote"], r["method"], r["error"] = hit[0], hit[1][:200], "page rules", None
        if r["price"] is None:
            r["error"] = r["error"] or "No verifiable price on page"
            return
        st = rule_stock(text)
        if st:
            r["in_stock"] = st[0]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, urls))

    stamp = now_iso()
    with _lock:
        cache = _read_cache(data_dir)
        if part.id in cache:
            cache[part.id].setdefault("prices", {}).update({u: {**v, "checked_at": stamp} for u, v in result.items()})
            _write_cache(data_dir, cache)
    return {"prices": result, "checked_at": stamp}


# ------------------------------------------------------------------ stage 3: use a verified price
class ApplyError(Exception):
    pass


def apply_price(part: Part, url: str, data_dir: Path = DATA_DIR) -> Part:
    """Copy a quote-verified price (and stock) from the sourcing cache into the part.

    The client only names the URL; the value comes from our own cache, which check_prices() filled
    after verifying the quote against the page text. So the UI can never inject an arbitrary price.
    """
    with _lock:
        entry = _read_cache(data_dir).get(part.id)
    rec = ((entry or {}).get("prices") or {}).get(url)
    if not rec or rec.get("price") is None or not rec.get("quote"):
        raise ApplyError("No verified price is stored for this link. Run 'Check live prices' first.")
    if rec.get("matches") is False:
        raise ApplyError("This page looks like a different product/variant, so its price was not applied.")
    stamp = rec.get("checked_at") or now_iso()
    ev = lambda q: Evidence(source_url=url, retrieved_at=stamp, method="scraped", quote=q)
    updated = part.model_copy(deep=True)
    updated.price = Spec(value=float(rec["price"]), unit="INR", evidence=ev(rec["quote"]))
    updated.url, updated.vendor = url, domain_of(url)
    if rec.get("in_stock") is not None:
        updated.in_stock = Spec(value=bool(rec["in_stock"]), unit=None, evidence=ev(rec["quote"]))
    return updated
