"""Gemini wrapper (google-genai SDK). Returns parsed JSON only."""
from __future__ import annotations

import json
import os
import re
import time

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-3.5-flash")


class LLMError(Exception):
    pass


def parse_json_loose(text: str) -> dict:
    """Parse JSON even if the model wrapped it in ``` fences or added chatter."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a == -1 or b <= a:
            raise LLMError("Model did not return JSON")
        try:
            out = json.loads(t[a:b + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}") from e
    if not isinstance(out, dict):
        raise LLMError("Model returned JSON that is not an object")
    return out


class GeminiClient:
    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise LLMError("Gemini API key is missing")
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:  # pragma: no cover
            raise LLMError("Package 'google-genai' is not installed (pip install google-genai)") from e
        self._types = types
        self._client = genai.Client(api_key=api_key)
        first = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self.models = [first] + [m for m in FALLBACK_MODELS if m != first]

    def json(self, prompt: str, system: str | None = None) -> dict:
        last_err: Exception | None = None
        for model in self.models:
            for attempt in (1, 2):
                try:
                    resp = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=self._types.GenerateContentConfig(
                            system_instruction=system,
                            response_mime_type="application/json",
                            temperature=0.0,
                        ),
                    )
                    text = resp.text
                    if not text:
                        raise LLMError("Gemini returned an empty response (it may have been blocked)")
                    return parse_json_loose(text)
                except LLMError as e:
                    last_err = e
                    if "invalid JSON" in str(e) and attempt == 1:
                        continue  # one retry for malformed JSON
                    raise
                except Exception as e:
                    msg = str(e)
                    low = msg.lower()
                    if "404" in msg or "not_found" in low or "not found" in low:
                        last_err = e
                        break  # try the next model name
                    if any(k in low for k in ("429", "resource_exhausted", "503", "unavailable", "overloaded")):
                        last_err = e
                        if attempt == 1:  # short back-off (honours 'retry in Ns' when Gemini says so), then retry once
                            m = re.search(r"retry(?:delay)?\D{0,12}(\d+(?:\.\d+)?)", low)
                            time.sleep(min(float(m.group(1)) if m else 3.0, 8.0))
                            continue
                        break  # still limited: other models have separate quotas, try the next one
                    raise LLMError(f"Gemini error: {msg}") from e
        raise LLMError(f"Gemini error: {last_err}" if last_err and "429" in str(last_err) else f"No Gemini model worked (tried {', '.join(self.models)}): {last_err}")
