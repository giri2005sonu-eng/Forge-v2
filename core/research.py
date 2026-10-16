"""TinyFish research step: Search + Fetch find build guides, Gemini lists the components each one states, with a verbatim quote."""
import json, os, re
from . import tf
from .pipeline import _generate, usable

ROLES = [("driver", ("l298", "l293", "tb6612", "drv88", "motor driver", "h-bridge", "h bridge", "motor shield")),
         ("controller", ("arduino", "esp32", "esp8266", "atmega", "stm32", "pico", "microcontroller", "nano", "uno")),
         ("motor", ("motor",)), ("battery", ("battery", "lipo", "li-ion", "18650", "power bank")),
         ("sensor", ("sensor", "tcrt", "qtr", "hc-sr04", "ultrasonic", "infrared")), ("chassis", ("chassis", "wheel", "caster", "frame"))]

def role_of(name):
    n = " " + name.lower() + " "
    return next((r for r, words in ROLES if any(w in n for w in words)), "other")

def _n(s): return re.sub(r"\s+", " ", s).strip().lower()

def extract_components(text, label, key):
    from google.genai import types
    prompt = (f'List the physical components this build guide says are needed for a "{label}" robot. Reply JSON: '
              '{"components":[{"name":"short part name","quote":"exact line or sentence copied from the page that mentions it"}]}. '
              'At most 15. Only parts the page actually states.\n\nPAGE:\n' + text[:12000])
    d = json.loads(_generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key).text)
    page = _n(text)
    return [dict(name=str(c["name"])[:60], quote=str(c["quote"])[:200]) for c in d.get("components", [])
            if c.get("name") and c.get("quote") and _n(str(c["quote"])) in page]  # kept only if the quote is on the page

def research(label, log=print):
    """Returns {guides:[url], items:[{name, role, quote, url}]}. Search and Fetch are free; Gemini does the reading."""
    key = os.getenv("GEMINI_API_KEY")
    hits = tf.search(f"{label} robot build guide components list")[:8]
    urls = [h["url"] for h in hits if h["url"] and usable(h["url"])][:3]
    log(f"Search: {len(hits)} results, reading {len(urls)} guides")
    pages = tf.fetch(urls) if urls else {}
    items, seen = [], set()
    for u in urls:
        if not pages.get(u): continue
        ck = f"r:{u}|{label}"; comps = tf.cache_get(ck)
        if comps is None:
            try: comps = extract_components(pages[u], label, key)
            except Exception as e: log(f"Gemini error: {str(e)[:140]}"); continue
            if comps: tf.cache_set(ck, comps)
        log(f"{len(comps)} verified components in {u}")
        for c in comps:
            k = (role_of(c["name"]), c["name"].lower())
            if k not in seen: seen.add(k); items.append(dict(c, role=k[0], url=u))
    return dict(guides=urls, items=items)
