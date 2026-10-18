"""TinyFish wrapper: Search and Fetch (free) plus the opt-in Web Agent (uses credits). Every call is cached on disk and the cache expires
(FORGE_CACHE_HOURS, default 72; 0 = never) so prices do not go stale."""
import hashlib, json, os, pathlib, threading, time
CACHE = pathlib.Path(__file__).resolve().parent.parent / ".cache"   # next to the project, not the folder you happen to run from
CACHE.mkdir(exist_ok=True)

_C = None

def _seconds(name, default):
    try: return max(1.0, float(os.getenv(name, default)))
    except ValueError: return float(default)

TIMEOUT_S = _seconds("FORGE_TINYFISH_TIMEOUT", 40)         # one Search call gives up after this many seconds
FETCH_TIMEOUT_S = _seconds("FORGE_TINYFISH_FETCH_TIMEOUT", 70)   # a Fetch reads several pages, so it gets longer

def with_timeout(fn, seconds, what="TinyFish"):
    """Run fn() and give up after `seconds` instead of hanging the app forever. The stuck call keeps running in a daemon thread
    (it cannot be killed) but nothing waits for it. Exceptions from fn are re-raised here."""
    box = {}
    def run():
        try: box["v"] = fn()
        except BaseException as e: box["e"] = e
    t = threading.Thread(target=run, daemon=True); t.start(); t.join(seconds)
    if t.is_alive(): raise TimeoutError(f"{what} did not answer within {seconds:.0f}s")
    if "e" in box: raise box["e"]
    return box.get("v")

def _client():
    """One shared client for the whole process (reads TINYFISH_API_KEY from the environment)."""
    global _C
    if _C is None:
        from tinyfish import TinyFish
        _C = TinyFish()
    return _C

def _call(fn):
    """Run an SDK call; if the HTTP client was closed underneath us, rebuild it and retry once."""
    global _C
    try:
        return fn()
    except RuntimeError as e:
        if "closed" not in str(e).lower(): raise
        _C = None
        return fn()

def _plain(o):
    if hasattr(o, "model_dump"): return o.model_dump()
    return o if isinstance(o, (dict, list, str, int, float, type(None))) else getattr(o, "__dict__", str(o))

def _file(key): return CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")

def _ttl_seconds():
    try: return max(0.0, float(os.getenv("FORGE_CACHE_HOURS", "72"))) * 3600
    except ValueError: return 72 * 3600

def _fresh(f):
    """A cache file counts only while it is younger than FORGE_CACHE_HOURS (0 = never expires)."""
    if not f.exists(): return False
    ttl = _ttl_seconds()
    return ttl == 0 or time.time() - f.stat().st_mtime <= ttl

def cache_get(key):
    f = _file(key)
    if not _fresh(f): return None
    try: return json.loads(f.read_text())
    except (ValueError, OSError): return None   # half-written by another thread: treat as a miss

def cache_set(key, val):
    f = _file(key); tmp = f.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(val, default=str)); tmp.replace(f)   # atomic, so parallel lookups never read a partial file

def _cached(key, fn, timeout=None):
    hit = cache_get(key)
    if hit is not None: return hit
    val = _plain(with_timeout(lambda: _call(fn), timeout or TIMEOUT_S)); cache_set(key, val); return val

def search(query, location="IN", language="en"):
    """Returns [{title,url,snippet}]. Search is free."""
    raw = _cached("s:" + query, lambda: _client().search.query(query, location=location, language=language))
    rows = raw.get("results", []) if isinstance(raw, dict) else raw
    return [dict(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("snippet", "")) for r in rows if isinstance(r, dict)]

def fetch(urls):
    """Returns {url: page_text}. Fetch is free. Tries common text fields since field names vary by format."""
    raw = _cached("f:" + "|".join(urls), lambda: _client().fetch.get_contents(urls=urls), timeout=FETCH_TIMEOUT_S)
    rows = raw.get("results", []) if isinstance(raw, dict) else raw
    out = {}
    for r in rows:
        if isinstance(r, dict):
            t = next((r[k] for k in ("text", "markdown", "content", "html") if isinstance(r.get(k), str) and r[k]), "")
            if r.get("url") and t: out[r["url"]] = t
    return out

CART_SCHEMA = {"type": "object", "properties": {"product_name": {"type": "string"}, "unit_price_inr": {"type": "number"}, "in_stock": {"type": "boolean"},
    "added_to_cart": {"type": "boolean"}, "cart_total_inr": {"type": "number"}, "delivery_estimate": {"type": "string"}}}
CART_GOAL = ("Add exactly one unit of this product to the cart. Do NOT click checkout, log in, sign up, or enter any payment or personal details. "
             "Then open the cart and report the product name, unit price in INR, whether it is in stock, the cart total and any delivery estimate. Stop as soon as you have them.")

_UNAVAILABLE = set()  # account-gated agent options TinyFish refused on this account: "strict", "max_steps", "max_duration"
_GATED = (("strict", ("strict",)), ("max_steps", ("max steps", "max_steps")), ("max_duration", ("max duration", "max_duration", "duration")))

def _refused_option(text):
    """TinyFish answers e.g. 'Your account is not enabled for custom max steps yet. Join the beta program at /beta, then retry.'
    Returns which option was refused ("strict" / "max_steps" / "max_duration"), or None for any other message."""
    t = str(text).lower()
    if "not enabled" not in t and "beta" not in t: return None
    return next((opt for opt, words in _GATED if any(w in t for w in words)), None)

def agent(url, goal=CART_GOAL, max_steps=12):
    """Web Agent run. USES CREDITS (about 1 per step per TinyFish pricing), so it only runs on a button click.
    It asks for strict mode, a step cap and a time cap. Accounts without those beta features get a refusal; each refused option is
    dropped (strict -> default mode, no custom step cap, no custom time cap), remembered for the session, and the run is retried.
    The result says what was really applied (mode, step_cap, time_cap) so the UI can be honest. The goal forbids checkout and
    entering any details in every case. Any other error (bad key, no credits) is raised as it is and never retried."""
    from tinyfish import AgentConfig
    key = f"a:{url}|{goal}|{max_steps}"
    hit = cache_get(key)
    if hit: return dict(hit, cached=True)

    def config():
        kw = dict(mode="default" if "strict" in _UNAVAILABLE else "strict")
        if "max_steps" not in _UNAVAILABLE: kw["max_steps"] = max_steps
        if "max_duration" not in _UNAVAILABLE: kw["max_duration_seconds"] = 180
        return kw

    for _ in range(len(_GATED) + 1):
        kw = config()
        try:
            res = _plain(_call(lambda: _client().agent.run(url=url, goal=goal, output_schema=CART_SCHEMA, agent_config=AgentConfig(**kw))))
        except Exception as e:
            opt = _refused_option(e)
            if opt is None or opt in _UNAVAILABLE: raise      # a bad key, no credits, or a refusal we already worked around: show it as it is
            _UNAVAILABLE.add(opt); continue
        opt = None if "COMPLETED" in str(res.get("status", "")).upper() else _refused_option(res.get("error"))
        if opt is None or opt in _UNAVAILABLE: break          # success, or a failure that is not an account restriction
        _UNAVAILABLE.add(opt)
    else:
        raise RuntimeError("TinyFish kept refusing the agent options for this account: " + ", ".join(sorted(_UNAVAILABLE)))
    res = dict(res, mode=kw["mode"], step_cap=kw.get("max_steps"), time_cap=kw.get("max_duration_seconds"))
    if "COMPLETED" in str(res.get("status", "")).upper(): cache_set(key, res)
    return res

def probe(query="Arduino Nano buy India"):
    """Print raw response shapes so you can confirm field names on your SDK version."""
    c = _client(); s = c.search.query(query); print("SEARCH:", json.dumps(_plain(s), default=str)[:800])
    urls = [r["url"] for r in search(query)[:1]]
    if urls: print("FETCH:", json.dumps(_plain(c.fetch.get_contents(urls=urls)), default=str)[:800])

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv(); probe()
