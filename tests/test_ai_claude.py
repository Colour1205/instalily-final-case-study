"""Tests for ClaudeProvider with a fake API client (no real AI calls, no API key needed)."""

import json

import pytest

from analysis.ai_claude import ClaudeProvider

GOOD_ANSWER = {"summary": "s", "why_good_lead": "w", "pitch": "p", "talking_points": ["a"], "draft_email": "e"}


class FakeBlock:
    """Stands in for one content block of the API response."""

    def __init__(self, block_type: str, text: str = "", content=None) -> None:
        """Remember the block type, its text and (for tool results) its content."""
        self.type = block_type
        self.text = text
        self.content = content


class FakePage:
    """Stands in for the content of a web fetch result."""

    def __init__(self, url: str, page_type: str = "web_fetch_result") -> None:
        """Remember the page address and whether the fetch worked."""
        self.type = page_type
        self.url = url


class FakeResponse:
    """Stands in for the API response: a list of content blocks and why the model stopped."""

    def __init__(self, blocks: list, stop_reason: str = "end_turn") -> None:
        """Remember the content blocks and the stop reason."""
        self.content = blocks
        self.stop_reason = stop_reason


class FakeMessages:
    """Stands in for client.messages: each create() returns the next prepared response."""

    def __init__(self, responses: list) -> None:
        """Remember the responses to return and record every request."""
        self.responses = responses
        self.requests = []

    def create(self, **kwargs) -> FakeResponse:
        """Return the next prepared response instead of calling the API."""
        self.requests.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    """Stands in for anthropic.Anthropic."""

    def __init__(self, responses: list) -> None:
        """Give the fake a messages attribute like the real client."""
        self.messages = FakeMessages(responses)


def make_provider(blocks: list) -> ClaudeProvider:
    """A ClaudeProvider whose API client is replaced by a fake returning these blocks."""
    return make_provider_with([FakeResponse(blocks)])


def make_provider_with(responses: list) -> ClaudeProvider:
    """A ClaudeProvider whose API client returns these responses one after another."""
    provider = ClaudeProvider("claude-haiku-5-5", "medium", 120.0, api_key="test-key")
    provider.client = FakeClient(responses)
    return provider


def test_returns_the_json_answer_as_a_dictionary():
    """The text block's JSON comes back as a dictionary; thinking blocks are skipped."""
    provider = make_provider([FakeBlock("thinking", ""), FakeBlock("text", json.dumps(GOOD_ANSWER))])
    assert provider._generate("system", "user") == GOOD_ANSWER


def test_answer_that_is_not_json_raises():
    """A refusal or cut-off answer is not valid JSON, so it raises and the job goes back to the queue."""
    with pytest.raises(json.JSONDecodeError):
        make_provider([FakeBlock("text", "I can't help with that.")])._generate("system", "user")
    with pytest.raises(json.JSONDecodeError):
        make_provider([FakeBlock("text", '{"summary": "cut o')])._generate("system", "user")


RESEARCH = {"website": "https://example.com", "about": "Roofing since 1998.", "people": ["Ann Lee (owner)"]}


def test_research_returns_the_answer_and_the_pages_read():
    """The JSON answer comes back with the addresses of the pages that were fetched successfully."""
    provider = make_provider([
        FakeBlock("server_tool_use"),
        FakeBlock("web_fetch_tool_result", content=FakePage("https://example.com/about")),
        FakeBlock("web_fetch_tool_result", content=FakePage("https://example.com/team", "web_fetch_tool_error")),
        FakeBlock("text", json.dumps(RESEARCH)),
    ])
    research = provider._research("system", "user")
    assert research["website"] == "https://example.com"
    assert research["people"] == ["Ann Lee (owner)"]
    assert research["sources"] == ["https://example.com/about"]


def test_research_blocks_gaf_and_continues_a_paused_turn():
    """gaf.com is blocked on both web tools, and a paused turn is sent back so Claude can finish."""
    provider = make_provider_with([
        FakeResponse([FakeBlock("server_tool_use")], stop_reason="pause_turn"),
        FakeResponse([FakeBlock("text", json.dumps(RESEARCH))]),
    ])
    assert provider._research("system", "user")["about"] == "Roofing since 1998."
    requests = provider.client.messages.requests
    assert len(requests) == 2
    assert requests[1]["messages"][1]["role"] == "assistant"
    for tool in requests[0]["tools"]:
        assert tool["blocked_domains"] == ["gaf.com"]


class FakeResult:
    """Stands in for one web search result."""

    def __init__(self, url: str) -> None:
        """Remember the result's address."""
        self.url = url


def test_research_sources_include_search_results_from_the_contractors_own_site():
    """Search results count as sources only when they are on the contractor's own website."""
    provider = make_provider([
        FakeBlock("web_search_tool_result", content=[
            FakeResult("https://www.example.com/about-us"), FakeResult("https://www.yelp.com/biz/example"),
        ]),
        FakeBlock("text", json.dumps(RESEARCH)),
    ])
    assert provider._research("system", "user")["sources"] == ["https://www.example.com/about-us"]


def test_research_drops_links_that_are_not_web_addresses():
    """A website or source that is not http(s), for example javascript:, never reaches the rep."""
    answer = {"website": "javascript:alert(1)", "about": "a", "people": []}
    provider = make_provider([
        FakeBlock("web_fetch_tool_result", content=FakePage("javascript:alert(2)")),
        FakeBlock("text", json.dumps(answer)),
    ])
    research = provider._research("system", "user")
    assert research["website"] == ""
    assert research["sources"] == []
