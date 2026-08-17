from __future__ import annotations

import re
import time
import urllib.parse
from difflib import SequenceMatcher

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    cffi_requests = None


class FoodNetworkSearcher:
    """Search foodnetwork.com for recipe pages (Chrome TLS impersonation)."""

    def __init__(self, *, delay_seconds: float = 0.25, timeout: float = 30.0) -> None:
        if cffi_requests is None:
            raise ImportError(
                "curl_cffi is required for Food Network search. "
                "Install with: pip install curl_cffi"
            )
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout = timeout
        self._last_request = 0.0
        self._cache: dict[str, list[dict]] = {}

    def search_page_url(self, query: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        return f"https://www.foodnetwork.com/search/{slug}-/SITE/recipes"

    def search(self, query: str) -> list[dict]:
        key = query.casefold().strip()
        if key in self._cache:
            return self._cache[key]
        self._throttle()
        url = self.search_page_url(query)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = cffi_requests.get(
                    url, impersonate="chrome", timeout=self.timeout
                )
                resp.raise_for_status()
                hits = _parse_search_html(resp.text)
                self._cache[key] = hits
                return hits
            except Exception as exc:  # network blips / temporary blocks
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Food Network search failed for {query!r}: {last_error}")

    def find_best_url(self, recipe_name: str, *, min_score: float = 0.62) -> dict | None:
        hits = self.search(recipe_name)
        if not hits:
            return None
        scored: list[dict] = []
        for hit in hits:
            score = _title_similarity(recipe_name, hit["title"] or hit["url"])
            # Prefer Food Network Kitchen (magazine-adjacent) slightly
            if "/food-network-kitchen/" in hit["url"]:
                score += 0.05
            scored.append({**hit, "score": score, "search_url": self.search_page_url(recipe_name)})
        scored.sort(key=lambda h: h["score"], reverse=True)
        best = scored[0]
        if best["score"] < min_score:
            return None
        return best

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.delay_seconds - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()


def _parse_search_html(html: str) -> list[dict]:
    urls = []
    for match in re.finditer(
        r"https://www\.foodnetwork\.com/recipes/[a-zA-Z0-9\-./]+", html
    ):
        url = match.group(0).rstrip(").,\"'")
        if "/recipes/photos/" in url or "/recipes/packages/" in url:
            continue
        urls.append(url)
    # Dedupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)

    results: list[dict] = []
    for url in ordered:
        title = _title_from_slug(url)
        results.append({"url": url, "title": title})
    return results


def _title_from_slug(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    slug = re.sub(r"-recipe-?\d*$", "", slug)
    slug = re.sub(r"-\d{5,}$", "", slug)
    words = slug.replace("-", " ").strip()
    return words


def _title_similarity(a: str, b: str) -> float:
    na = _norm_title(a)
    nb = _norm_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return seq
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return max(seq, overlap)


def _norm_title(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stop = {"recipe", "recipes", "the", "a", "an", "and", "with", "food", "network"}
    tokens = [t for t in text.split() if t and t not in stop]
    return " ".join(tokens)
