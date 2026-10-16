import itertools, json, os, re, time
from . import resume as resume_mod, tf
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


def extract_resume_factors(text):
    """Use Gemini only to structure resume evidence; unsupported claims are removed locally."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Add GEMINI_API_KEY to analyze a resume. You can still get recommendations from the survey alone.")
    from google.genai import types
    prompt = (
        "Extract only explicit facts from this student's resume. Do not infer proficiency. Return JSON with these arrays: "
        '"skills":[{"id":"allowed_id","name":"short label","quote":"exact verbatim evidence"}], '
        '"languages":[{"id":"c_cpp|python","name":"language","quote":"exact verbatim evidence"}], '
        '"tools":[{"id":"soldering_iron|multimeter|3d_printer|college_lab|laptop","name":"tool","quote":"exact verbatim evidence"}], '
        '"projects":[{"name":"project name","domain":"embedded|robotics|vision|iot|mechanics|other",'
        '"skills":["skill"],"quote":"exact verbatim evidence"}]. '
        "Allowed skill IDs: sensor_read, soldering, motor_driver, breadboard, raspberry_pi, trained_model. "
        "Every item MUST include a short exact quote copied character-for-character from the resume. Omit items without evidence. "
        "Return empty arrays when there are no supported facts.\n\nRESUME TEXT:\n" + text[:resume_mod.MAX_CHARS]
    )
    try:
        response = _generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key)
        extracted = json.loads(response.text or "{}")
    except Exception as error:
        raise ValueError(f"Gemini could not structure this resume ({type(error).__name__}).") from error
    return resume_mod.validate_factors(text, extracted)


def research_career_target(target):
    """Search and fetch public job/career pages; return source excerpts and deterministic domain signals."""
    target = str(target or "").strip()[:160]
    if not target:
        return dict(query="", signals=[], sources=[])
    query = f'"{target}" job skills requirements robotics embedded India'
    hits = tf.search(query, location="IN")[:5]
    urls, seen = [], set()
    for hit in hits:
        url = hit.get("url", "")
        if url.startswith(("https://", "http://")) and url not in seen:
            urls.append(url)
            seen.add(url)
        if len(urls) == 3:
            break
    pages = tf.fetch(urls) if urls else {}
    sources, searchable = [], [target.lower()]
    for hit in hits:
        url = hit.get("url", "")
        content = " ".join(str(pages.get(url, "") or hit.get("snippet", "")).split())[:1400]
        if not url or not content:
            continue
        sources.append(dict(title=str(hit.get("title", "Career source"))[:160], url=url, excerpt=content))
        searchable.append((str(hit.get("title", "")) + " " + content).lower())
    combined = " ".join(searchable)
    terms = {
        "embedded": ("embedded", "firmware", "microcontroller", "rtos", "stm32"),
        "robotics": ("robotics", "robot", "autonomous", "control systems"),
        "vision": ("computer vision", "opencv", "image processing", "machine learning", "deep learning"),
        "iot": ("iot", "wireless", "mqtt", "bluetooth", "connectivity"),
        "mechanics": ("mechanical", "cad", "fabrication", "solidworks", "3d printing"),
    }
    signals = [tag for tag, phrases in terms.items() if any(phrase in combined for phrase in phrases)]
    return dict(query=query, signals=signals, sources=sources)

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
    """Conservatively map a short idea by keywords; recommendation choices never call Gemini."""
    idea = str(text or "").lower()
    rules = (("line_follower", ("line follower", "follows a line", "follow the line", "black path", "black line")),
             ("obstacle_avoider", ("obstacle", "avoid objects", "avoid collision")),
             ("bluetooth_car", ("bluetooth", "phone controlled", "phone control")))
    for project, phrases in rules:
        if any(phrase in idea for phrase in phrases):
            return dict(project=project, reason="Matched by a deterministic keyword rule to a supported build.")
    return dict(project=None, reason="No supported BOM project clearly matches this idea yet.")
