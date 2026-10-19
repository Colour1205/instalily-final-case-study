"""Tests for OllamaProvider with a fake HTTP call (no Ollama server needed)."""

import json

import httpx
import pytest

from analysis import ollama_provider
from analysis.ollama_provider import OllamaProvider
from analysis.abstract_provider import ANALYSIS_SCHEMA

GOOD_ANSWER = {"summary": "s", "why_good_lead": "w", "pitch": "p", "talking_points": ["a"], "draft_email": "e"}


class FakeResponse:
    """Stands in for httpx's response: a status code and Ollama's JSON body."""

    def __init__(self, content: str, status_code: int = 200) -> None:
        """Remember the model's text answer and the HTTP status."""
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise like httpx does for an error status."""
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict:
        """Ollama's chat reply, with the model's answer as text."""
        return {"message": {"role": "assistant", "content": self.content}}


def fake_post(response: FakeResponse, sent: list):
    """A stand-in for httpx.post that records the request and returns the prepared response."""

    def post(url, json, timeout):
        """Record the call instead of sending it."""
        sent.append({"url": url, "json": json, "timeout": timeout})
        return response

    return post


def test_sends_the_prompts_with_the_schema_and_parses_the_answer(monkeypatch):
    """The system and user prompts go to /api/chat with the JSON schema; the JSON answer comes back as a dictionary."""
    sent = []
    monkeypatch.setattr(ollama_provider.httpx, "post", fake_post(FakeResponse(json.dumps(GOOD_ANSWER)), sent))
    provider = OllamaProvider("http://pc:11434/", "lili-analyst-1.7b", 120.0)
    assert provider._generate("system", "user") == GOOD_ANSWER
    request = sent[0]
    assert request["url"] == "http://pc:11434/api/chat"
    assert request["json"]["model"] == "lili-analyst-1.7b"
    assert request["json"]["format"] == ANALYSIS_SCHEMA
    assert request["json"]["stream"] is False
    assert request["json"]["messages"] == [{"role": "system", "content": "system"}, {"role": "user", "content": "user"}]


def test_bad_answers_and_server_errors_raise(monkeypatch):
    """Text that is not JSON, or an HTTP error, raises, so the job goes back to the queue."""
    provider = OllamaProvider("http://pc:11434", "lili-analyst-1.7b", 120.0)
    monkeypatch.setattr(ollama_provider.httpx, "post", fake_post(FakeResponse("not json"), []))
    with pytest.raises(json.JSONDecodeError):
        provider._generate("system", "user")
    monkeypatch.setattr(ollama_provider.httpx, "post", fake_post(FakeResponse("", status_code=500), []))
    with pytest.raises(httpx.HTTPStatusError):
        provider._generate("system", "user")
