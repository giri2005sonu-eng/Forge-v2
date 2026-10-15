"""Thin REST client for TinyFish Search + Fetch with CLI fallback and retry logic."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.search.tinyfish.ai"
FETCH_URL = "https://api.fetch.tinyfish.ai"


class TinyFishError(Exception):
    pass


class TinyFishClient:
    def __init__(self, api_key: str, session: Optional[requests.Session] = None, timeout: int = 60):
        if not api_key:
            raise TinyFishError("TinyFish API key is missing")
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key}
        self._s = session or requests.Session()
        self._timeout = timeout

    @staticmethod
    def _raise(resp: requests.Response) -> None:
        if resp.status_code in (401, 403):
            raise TinyFishError(f"TinyFish rejected the API key (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise TinyFishError("TinyFish rate limit hit (HTTP 429) - wait a moment and retry")
        if resp.status_code >= 400:
            raise TinyFishError(f"TinyFish error HTTP {resp.status_code}: {resp.text[:200]}")

    def _cli_search(self, query: str) -> list[dict]:
        """Fallback to tinyfish CLI if available."""
        exe = shutil.which("tinyfish")
        if not exe:
            return []
        env = dict(os.environ, TINYFISH_API_KEY=self.api_key)
        try:
            res = subprocess.run([exe, "search", "query", query], capture_output=True, text=True, timeout=self._timeout, env=env)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                return list(data.get("results", []))
        except Exception as e:
            logger.debug("TinyFish CLI search fallback error: %s", e)
        return []

    def _cli_fetch(self, urls: list[str]) -> tuple[list[dict], list[dict]]:
        """Fallback to tinyfish CLI fetch if available."""
        exe = shutil.which("tinyfish")
        if not exe or not urls:
            return [], []
        env = dict(os.environ, TINYFISH_API_KEY=self.api_key)
        try:
            cmd = [exe, "fetch", "content", "get"] + urls[:10]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout, env=env)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                return list(data.get("results", [])), list(data.get("errors", []))
        except Exception as e:
            logger.debug("TinyFish CLI fetch fallback error: %s", e)
        return [], []

    def search(self, query: str, max_retries: int = 2) -> list[dict]:
        for attempt in range(max_retries + 1):
            try:
                r = self._s.get(SEARCH_URL, params={"query": query}, headers=self._headers, timeout=self._timeout)
                if r.status_code == 429 and attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                self._raise(r)
                data = r.json()
                return list(data.get("results", []))
            except (requests.RequestException, TinyFishError) as e:
                if attempt == max_retries:
                    # Try CLI fallback before failing completely
                    cli_res = self._cli_search(query)
                    if cli_res:
                        return cli_res
                    if isinstance(e, TinyFishError):
                        raise
                    raise TinyFishError(f"TinyFish search request failed: {e}") from e
                time.sleep(0.5 * (attempt + 1))
        return []

    def fetch(self, urls: list[str], ttl: Optional[int] = 0, max_retries: int = 2) -> tuple[list[dict], list[dict]]:
        """Returns (pages, errors). ttl=0 asks for a live fetch (fresh prices)."""
        if not urls:
            return [], []
        body: dict = {"urls": urls[:10], "format": "markdown"}
        if ttl is not None:
            body["ttl"] = ttl

        for attempt in range(max_retries + 1):
            try:
                r = self._s.post(FETCH_URL, json=body, headers=self._headers, timeout=self._timeout)
                if r.status_code == 400 and "ttl" in body:  # be tolerant if ttl is rejected
                    body.pop("ttl", None)
                    r = self._s.post(FETCH_URL, json=body, headers=self._headers, timeout=self._timeout)
                if r.status_code == 429 and attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                self._raise(r)
                data = r.json()
                return list(data.get("results", [])), list(data.get("errors", []))
            except (requests.RequestException, TinyFishError) as e:
                if attempt == max_retries:
                    # Try CLI fallback
                    cli_pages, cli_errs = self._cli_fetch(urls)
                    if cli_pages:
                        return cli_pages, cli_errs
                    if isinstance(e, TinyFishError):
                        raise
                    raise TinyFishError(f"TinyFish fetch request failed: {e}") from e
                time.sleep(0.5 * (attempt + 1))
        return [], []
