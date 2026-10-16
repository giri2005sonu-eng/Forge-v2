"""Spec check: compare our typed seed specs with values stated on the fetched shop pages. Shown as a diff; never applied silently."""
import json, os, re
from . import tf
from .pipeline import _generate

HINTS = {"controller": dict(vin_min_v="minimum input voltage on VIN (V)", vin_max_v="maximum input voltage on VIN (V)", logic_v="operating logic voltage (V)"),
         "driver": dict(supply_min_v="minimum motor supply voltage (V)", supply_max_v="maximum motor supply voltage (V)", max_a="max continuous current per channel (A)"),
         "motor": dict(min_v="minimum rated voltage (V)", max_v="maximum rated voltage (V)", stall_a="stall current (A)"),
         "battery": dict(nominal_v="nominal voltage (V)", max_v="fully charged voltage (V)"),
         "sensor": dict(supply_min_v="minimum supply voltage (V)", supply_max_v="maximum supply voltage (V)")}

def find_specs(part, text, key):
    """{spec: {value, quote}} for values the page states, each kept only if its quote is on the page and contains the number."""
    from google.genai import types
    hints = {k: v for k, v in HINTS.get(part["role"], {}).items() if k in part["specs"]}
    if not hints: return {}
    prompt = (f'From this product page for "{part["name"]}", find these values. Reply JSON mapping each key to '
              '{"value":number|null,"quote":"exact text copied from the page"}; use null if the page does not state it.\nKeys: ' + json.dumps(hints) + "\n\nPAGE:\n" + text[:12000])
    d = json.loads(_generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key).text)
    page, out = re.sub(r"\s+", " ", text).lower(), {}
    for k in hints:
        v, q = (d.get(k) or {}).get("value"), str((d.get(k) or {}).get("quote") or "")
        if isinstance(v, (int, float)) and q and re.sub(r"\s+", " ", q).lower() in page and str(v).rstrip("0").rstrip(".") in q.replace(",", ""):
            out[k] = dict(value=float(v), quote=q[:160])
    return out

def compare(part, found, tol=0.1):
    rows = []
    for k in HINTS.get(part["role"], {}):
        if k not in part["specs"]: continue
        seed, f = part["specs"][k], found.get(k)
        st = "not stated" if not f else "match" if abs(f["value"] - seed) <= tol * abs(seed) else "differs"
        rows.append(dict(spec=k, seed=seed, live=f["value"] if f else None, status=st, quote=f["quote"] if f else "", url=f.get("url", "") if f else ""))
    return rows

def check_part(part, pages, log=print):
    """pages: {url: text}. Takes the first page that states each spec."""
    key, found = os.getenv("GEMINI_API_KEY"), {}
    for u, text in pages.items():
        ck = f"sp:{u}|{part['id']}"; got = tf.cache_get(ck)
        if got is None:
            try: got = find_specs(part, text, key)
            except Exception as e: log(f"Gemini error: {str(e)[:140]}"); continue
            if got: tf.cache_set(ck, got)
        for k, v in got.items(): found.setdefault(k, dict(v, url=u))
    return compare(part, found)
