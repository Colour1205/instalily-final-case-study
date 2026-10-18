"""Claude provider: sends the prompt to Anthropic's API and returns the JSON answer as a dictionary."""

import json

import anthropic

from analysis.ai_provider import ANALYSIS_SCHEMA, AbstractAIProvider


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
