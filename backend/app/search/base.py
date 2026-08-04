"""搜索 Provider 的业务无关契约。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str
    published_at: str | None = None


class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """按查询词返回可供 LLM 引用的网页结果。"""
