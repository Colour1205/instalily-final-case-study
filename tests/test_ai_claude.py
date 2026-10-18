"""Tests for ClaudeProvider with a fake API client (no real AI calls, no API key needed)."""

import json

import pytest

from analysis.ai_claude import ClaudeProvider

GOOD_ANSWER = {"summary": "s", "why_good_lead": "w", "pitch": "p", "talking_points": ["a"], "draft_email": "e"}


class FakeBlock:
    """Stands in for one content block of the API response."""

    def __init__(self, block_type: str, text: str) -> None:
        """Remember the block type and its text."""
        self.type = block_type
        self.text = text


class FakeResponse:
    """Stands in for the API response: a list of content blocks."""

    def __init__(self, blocks: list) -> None:
        """Remember the content blocks."""
        self.content = blocks


class FakeMessages:
    """Stands in for client.messages: create() returns a prepared response."""

    def __init__(self, response: FakeResponse) -> None:
        """Remember the response to return."""
        self.response = response

    def create(self, **kwargs) -> FakeResponse:
        """Return the prepared response instead of calling the API."""
        return self.response


class FakeClient:
    """Stands in for anthropic.Anthropic."""

    def __init__(self, response: FakeResponse) -> None:
        """Give the fake a messages attribute like the real client."""
        self.messages = FakeMessages(response)


def make_provider(blocks: list) -> ClaudeProvider:
    """A ClaudeProvider whose API client is replaced by a fake returning these blocks."""
    provider = ClaudeProvider("claude-haiku-5-5", "medium", 120.0, api_key="test-key")
    provider.client = FakeClient(FakeResponse(blocks))
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
