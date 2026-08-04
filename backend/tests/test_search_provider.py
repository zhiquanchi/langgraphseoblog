import json

from app.search.tavily import TavilySearchProvider


def test_tavily_search_maps_results_and_does_not_request_generated_answer(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "LangGraph guide",
                            "url": "https://example.com/guide",
                            "content": "A concise guide.",
                            "raw_content": "Full guide content.",
                            "published_date": "2026-01-02",
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.search.tavily.request.urlopen", fake_urlopen)
    results = TavilySearchProvider("test-key").search("LangGraph tutorial", max_results=3)

    assert results[0].title == "LangGraph guide"
    assert results[0].content == "Full guide content."
    assert captured["body"]["include_answer"] is False
    assert captured["body"]["include_raw_content"] == "markdown"
    assert captured["body"]["search_depth"] == "basic"
    assert captured["timeout"] == 15
