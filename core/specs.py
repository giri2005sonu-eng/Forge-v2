"""Spec check: compare our typed seed specs with values stated on the fetched shop pages. Shown as a diff; never applied silently.
Works for every part that has typed numeric specs (catalog parts and the whole parts library, see part_specs.py)."""
import json, os, re
from . import part_specs, tf
from .pipeline import _generate

BATCH = 12   # spec keys per Gemini call: one call per page covers a whole part

def hint(key):
    label, unit, _ = part_specs.meta(key)
    return f"{label.lower()} ({unit})" if unit else label.lower()

def checkable(part):
    """The numeric spec keys of this part we know how to describe to the reader (booleans and text such as 'I2C' are not number-checked)."""
    return list(part_specs.numeric_specs(part.get("specs")))

def has_number(quote, value, unit=""):
    """True only if a whole number in the quote equals the value, so 0.8 does not match '0.85' and 5 does not match '1,250'.
    For amp values a quote in milliamps ('800 mA') also counts."""
    for tok in re.findall(r"\d[\d,]*\.?\d*", quote.replace("−", "-")):
        try: n = float(tok.replace(",", ""))
        except ValueError: continue
        if abs(n - value) < 1e-9 or (unit == "A" and "ma" in quote.lower() and abs(n / 1000 - value) < 1e-9): return True
    return False

def find_specs(part, text, key):
    """{spec: {value, quote}} for values the page states, each kept only if its quote is on the page and contains the number."""
    from google.genai import types
    keys = checkable(part)
    if not keys: return {}
    page, out = re.sub(r"\s+", " ", text).lower(), {}
    for i in range(0, len(keys), BATCH):
        hints = {k: hint(k) for k in keys[i:i + BATCH]}
        prompt = (f'From this product page for "{part["name"]}", find these values. Reply JSON mapping each key to '
                  '{"value":number|null,"quote":"exact text copied from the page"}; use null if the page does not state it. '
                  'Give the value in the unit shown in brackets.\nKeys: ' + json.dumps(hints) + "\n\nPAGE:\n" + text[:12000])
        d = json.loads(_generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key).text)
        for k in hints:
            v, q = (d.get(k) or {}).get("value"), str((d.get(k) or {}).get("quote") or "")
            if part_specs.is_number(v) and q and re.sub(r"\s+", " ", q).lower() in page and has_number(q, v, part_specs.unit(k)):
                out[k] = dict(value=float(v), quote=q[:160])
    return out

def compare(part, found, tol=0.1):
    rows = []
    for k in checkable(part):
        seed, f = part["specs"][k], found.get(k)
        st = "not stated" if not f else "match" if abs(f["value"] - seed) <= tol * abs(seed) else "differs"
        rows.append(dict(spec=k, label=part_specs.meta(k)[0], unit=part_specs.unit(k), seed=seed, live=f["value"] if f else None, status=st,
                         delta_pct=(round((f["value"] - seed) / seed * 100) if f and seed else None), quote=f["quote"] if f else "", url=f.get("url", "") if f else ""))
    return rows

def summarize(rows):
    """{'match': n, 'differs': n, 'not stated': n} for a one-line headline above the rows."""
    return {s: sum(r["status"] == s for r in rows) for s in ("match", "differs", "not stated")}

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
