"""TinyFish wrapper: Search + Fetch only (both free; no Agent/Browser, which use credits). Every call is cached on disk."""
import hashlib, json, pathlib
CACHE = pathlib.Path(".cache"); CACHE.mkdir(exist_ok=True)

_C = None

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

def _cached(key, fn):
    f = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if f.exists(): return json.loads(f.read_text())
    val = _plain(_call(fn)); f.write_text(json.dumps(val, default=str)); return val

def _file(key): return CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")
def cache_get(key):
    f = _file(key); return json.loads(f.read_text()) if f.exists() else None
def cache_set(key, val): _file(key).write_text(json.dumps(val, default=str))

def search(query, location="IN", language="en"):
    """Returns [{title,url,snippet}]. Search is free."""
    raw = _cached("s:" + query, lambda: _client().search.query(query, location=location, language=language))
    rows = raw.get("results", []) if isinstance(raw, dict) else raw
    return [dict(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("snippet", "")) for r in rows if isinstance(r, dict)]

def fetch(urls):
    """Returns {url: page_text}. Fetch is free. Tries common text fields since field names vary by format."""
    raw = _cached("f:" + "|".join(urls), lambda: _client().fetch.get_contents(urls=urls))
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

def agent(url, goal=CART_GOAL, max_steps=12):
    """Web Agent run. USES CREDITS (about 1 per step per TinyFish pricing), so it is capped at max_steps and only runs on a button click."""
    from tinyfish import AgentConfig
    key = f"a:{url}|{goal}|{max_steps}"
    hit = cache_get(key)
    if hit: return dict(hit, cached=True)
    res = _plain(_call(lambda: _client().agent.run(url=url, goal=goal, output_schema=CART_SCHEMA,
        agent_config=AgentConfig(mode="strict", max_steps=max_steps, max_duration_seconds=180))))
    if "COMPLETED" in str(res.get("status", "")).upper(): cache_set(key, res)
    return res

def probe(query="Arduino Nano buy India"):
    """Print raw response shapes so you can confirm field names on your SDK version."""
    c = _client(); s = c.search.query(query); print("SEARCH:", json.dumps(_plain(s), default=str)[:800])
    urls = [r["url"] for r in search(query)[:1]]
    if urls: print("FETCH:", json.dumps(_plain(c.fetch.get_contents(urls=urls)), default=str)[:800])

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv(); probe()
