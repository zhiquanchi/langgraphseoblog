"""可替换的实时搜索 Provider。"""

import os

from .base import SearchProvider, SearchResult
from .tavily import TavilySearchProvider


class SearchProviderNotConfiguredError(RuntimeError):
    """没有配置可用的实时搜索 Provider。"""


def get_search_provider() -> SearchProvider:
    provider = os.environ.get("SEARCH_PROVIDER", "tavily").strip().lower()
    if provider != "tavily":
        raise SearchProviderNotConfiguredError(f"不支持的搜索 Provider: {provider}")
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise SearchProviderNotConfiguredError("未配置 TAVILY_API_KEY")
    return TavilySearchProvider(api_key)


__all__ = ["SearchProvider", "SearchResult", "SearchProviderNotConfiguredError", "get_search_provider"]
