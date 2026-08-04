"""Tavily Search API 适配器。"""

import json
from urllib import request
from urllib.error import HTTPError, URLError

from .base import SearchResult


class TavilySearchError(RuntimeError):
    """Tavily 请求失败。"""


class TavilySearchProvider:
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, *, timeout: int = 15) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": "markdown",
            "max_results": max(1, min(max_results, 10)),
        }
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TavilySearchError(f"Tavily 搜索失败: {exc}") from exc

        raw_results = body.get("results", [])
        if not isinstance(raw_results, list):
            raise TavilySearchError("Tavily 返回结果格式无效")
        results: list[SearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            content = item.get("raw_content") or item.get("content")
            if not all(isinstance(value, str) and value.strip() for value in (title, url, content)):
                continue
            results.append(
                SearchResult(
                    title=title.strip(),
                    url=url.strip(),
                    content=content.strip(),
                    published_at=item.get("published_date")
                    if isinstance(item.get("published_date"), str)
                    else None,
                )
            )
        return results
