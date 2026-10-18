"""Claude provider: sends the prompt to Anthropic's API and returns the JSON answer as a dictionary."""

import json
from urllib.parse import urlparse

import anthropic

from analysis.ai_provider import ANALYSIS_SCHEMA, RESEARCH_SCHEMA, AbstractAIProvider

# Web tools for research. The basic versions used about a third of the tokens in a test.
# gaf.com is blocked: it refuses bots, and we respect that.
SEARCH_CENTRE = {"type": "approximate", "city": "New York", "region": "New York", "country": "US",
                 "timezone": "America/New_York"}
RESEARCH_TOOLS = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 1, "blocked_domains": ["gaf.com"],
     "user_location": SEARCH_CENTRE},
    {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 2, "blocked_domains": ["gaf.com"],
     "max_content_tokens": 3000},
]


class ClaudeProvider(AbstractAIProvider):
    """Child class that asks a Claude model (Claude Haiku 5.5 by default) for each analysis."""

    def __init__(self, model: str, effort: str, timeout_seconds: float, api_key: str) -> None:
        """Create the API client. An empty api_key makes the SDK read ANTHROPIC_API_KEY instead."""
        self.model = model
        self.effort = effort
        # One library retry is enough: the job queue retries failed jobs itself.
        self.client = anthropic.Anthropic(api_key=api_key or None, timeout=timeout_seconds, max_retries=1)

    def _generate(self, system_prompt: str, user_prompt: str) -> dict:
        """Ask Claude for one analysis in the ANALYSIS_SCHEMA shape and parse its JSON text."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            # The system prompt is the same for every contractor, so it is cached between calls.
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}, "effort": self.effort},
        )
        answer = ""
        for block in response.content:
            if block.type == "text":
                answer = block.text
        # Not valid JSON (for example a refusal or a cut-off answer) raises an error here.
        return json.loads(answer)

    def _research(self, system_prompt: str, user_prompt: str) -> dict:
        """Let Claude search the web and read the contractor's site, then parse its RESEARCH_SCHEMA answer."""
        messages = [{"role": "user", "content": user_prompt}]
        # A long web-tool turn can pause; sending it back lets Claude continue (at most 3 times).
        for _ in range(3):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                # Searching and reading pages takes longer than a normal answer.
                timeout=180,
                system=system_prompt,
                messages=messages,
                tools=RESEARCH_TOOLS,
                output_config={"format": {"type": "json_schema", "schema": RESEARCH_SCHEMA}, "effort": "low"},
            )
            if response.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": response.content}]

        answer = ""
        read = []
        found = []
        for block in response.content:
            if block.type == "text":
                answer = block.text
            if block.type == "web_fetch_tool_result" and getattr(block.content, "type", "") == "web_fetch_result":
                read.append(block.content.url)
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                for result in block.content:
                    found.append(result.url)
        research = json.loads(answer)
        # Links come from the web: keep only normal web addresses (no javascript: or other schemes).
        if not research["website"].startswith(("http://", "https://")):
            research["website"] = ""

        # Sources shown to the rep: pages Claude read, plus search results from the contractor's own site.
        site = urlparse(research["website"]).netloc.removeprefix("www.")
        sources = []
        for url in read + found:
            own_site = site != "" and urlparse(url).netloc.removeprefix("www.") == site
            web = url.startswith(("http://", "https://"))
            if web and url not in sources and (url in read or own_site):
                sources.append(url)
        research["sources"] = sources
        return research
