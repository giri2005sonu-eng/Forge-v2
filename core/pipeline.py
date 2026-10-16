import itertools, json, os, re, time
from . import tf
from .data import CATALOG, EXTRAS, NONE_SENSOR, PROJECTS, QTY, RULES
from .rules import evaluate

MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]  # tried in order if one is unavailable or out of quota
_G = None

def _gemini(key):
    """Keep ONE Gemini client alive. google-genai closes a client when Python discards it,
    so chaining genai.Client(...).models.generate_content(...) fails with 'client has been closed'."""
    global _G
    if _G is None:
        from google import genai
        _G = genai.Client(api_key=key)
    return _G

GONE = ("404", "NOT_FOUND")
BUSY = ("503", "UNAVAILABLE", "500", "INTERNAL", "429", "RESOURCE_EXHAUSTED")

def _generate(prompt, cfg, key):
    """Try the configured model, then fallbacks. Busy/quota errors get one retry after a pause; missing models move on at once."""
    last = None
    for m in dict.fromkeys([os.getenv("GEMINI_MODEL") or MODELS[0], *MODELS]):
        for attempt in range(2):
            try:
                return _gemini(key).models.generate_content(model=m, contents=prompt, config=cfg)
            except Exception as e:
                last, msg = e, str(e)
                if any(g in msg for g in GONE): break
                if any(x in msg for x in BUSY):
                    if attempt == 0: time.sleep(2); continue
                    break
                raise
    raise last

def extract_offer(page_text, part_name):
    """Gemini reads the page; a price is accepted ONLY if its quote appears verbatim in the page and contains the number."""
    key = os.getenv("GEMINI_API_KEY")
    if not key: return None
    from google.genai import types
    prompt = (f'From this product page, find the price in INR of "{part_name}" (the main product, not related items) and stock status. '
              'Reply JSON: {"product_name":"exact product title copied from the page","price_inr":number|null,"in_stock":true|false|null,"quote":"exact text copied from the page showing the price"}. '
              'Use null if unsure.\n\nPAGE:\n' + page_text[:12000])
    r = _generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key)
    try: d = json.loads(r.text)
    except Exception: return None
    q, p = d.get("quote") or "", d.get("price_inr")
    digits = str(int(p)) if isinstance(p, (int, float)) else ""
    if not q or q not in page_text or not digits or digits not in re.sub(r"[,\s]", "", q): return None
    n = (d.get("product_name") or "").strip()
    name = n[:90] if n and n.lower() in page_text.lower() else None  # verbatim on the page, or not shown
    return dict(price=float(p), in_stock=d.get("in_stock"), quote=q, name=name)

BLOCKED = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "pinterest.", "reddit.com", "quora.com", "wikipedia.org", "github.com", "cirkitdesigner.com")

def usable(url):
    """Skip videos, social posts, simulators and category listings; keep likely product pages."""
    return not any(b in url for b in BLOCKED) and "/product-category/" not in url

def source_part(part, log=print):
    """Search -> Fetch -> verified extraction for one part. Returns offers (price None if unverified)."""
    hits = tf.search(part["query"] + " buy India price")[:8]
    urls = [h["url"] for h in hits if h["url"] and usable(h["url"])][:4]
    log(f"Search: {len(hits)} results for {part['name']} ({len(urls)} look like shop pages)")
    pages = tf.fetch(urls) if urls else {}
    offers = []
    for u in urls:
        ck = f"x:{u}|{part['name']}"
        o = tf.cache_get(ck)  # only verified reads are cached, so failures are retried next time
        if o is None and pages.get(u):
            try: o = extract_offer(pages[u], part["name"])
            except Exception as e: log(f"Gemini error: {str(e)[:160]}")
            if o: tf.cache_set(ck, o)
        offers.append(dict(url=u, **(o or dict(price=None, in_stock=None, quote=None, name=None))))
        log(("Verified ₹%s at " % o["price"] if o else "No verifiable price at ") + u)
    return offers

def spread_warning(offers, ratio=3.0):
    """Warn when verified prices for one part differ a lot: usually different products or variants (e.g. clone vs original)."""
    v = [o["price"] for o in offers if o.get("price")]
    if len(v) >= 2 and max(v) / min(v) > ratio:
        return f"Verified prices range ₹{min(v):,.0f} to ₹{max(v):,.0f}. These are likely different products or variants; check the names. The BOM uses the cheapest."

def price_of(part, live):
    vals = [o["price"] for o in live.get(part["id"], []) if o.get("price")]
    return (min(vals), "live") if vals else (part["seed_price"], "seed")

def select(robot, budget, needs_bt=False, live=None):
    live = live or {}
    by = {r: [p for p in CATALOG if p["role"] == r] for r in ("controller", "driver", "motor", "battery", "sensor")}
    kind = PROJECTS[robot]["sensor"]
    by["sensor"] = [NONE_SENSOR] if kind is None else [p for p in by["sensor"] if p["kind"] == kind]
    rows = []
    for combo in itertools.product(*by.values()):
        parts = {**dict(zip(by.keys(), combo)), **{e["role"]: e for e in EXTRAS}}
        cost = sum(price_of(p, live)[0] * QTY.get(r, 1) for r, p in parts.items())
        checks = evaluate(parts, RULES, needs_bt)
        rows.append(dict(parts=parts, cost=cost, checks=checks, fails=sum(c["status"] == "FAIL" for c in checks), unknown=sum(c["status"] == "UNKNOWN" for c in checks)))
    ok = sorted([r for r in rows if r["fails"] == 0 and r["cost"] <= budget], key=lambda r: (r["unknown"], r["cost"]))
    return dict(best=ok[0] if ok else None, alternatives=ok[1:4], evaluated=len(rows), rejected=sum(r["fails"] > 0 for r in rows))


def map_idea(text):
    """Gemini maps a free-text idea onto a supported project type, or says honestly that it can't."""
    key = os.getenv("GEMINI_API_KEY")
    if not key: return dict(project=None, reason="Add a Gemini key to match your own idea.")
    from google.genai import types
    opts = "\n".join(f"- {k}: {v['label']} ({v['desc']})" for k, v in PROJECTS.items())
    prompt = ("A student describes a robot project idea. Pick the supported type whose parts and compatibility rules would fit it "
              "(wheeled robot with DC motors, controller, driver, battery, optional line or distance sensor). If none fits, e.g. a drone, "
              "walking robot or robot arm, answer null.\nSupported:\n" + opts +
              '\nReply JSON: {"project": key or null, "reason": "one short sentence"}\nIDEA: ' + text[:500])
    try: d = json.loads(_generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key).text)
    except Exception as e: return dict(project=None, reason=f"Could not match: {str(e)[:100]}")
    return dict(project=d.get("project") if d.get("project") in PROJECTS else None, reason=str(d.get("reason", ""))[:200])
