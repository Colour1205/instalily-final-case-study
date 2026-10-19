"""Ollama provider: sends the prompt to a model served by Ollama and returns the JSON answer as a dictionary."""

import json

import httpx

from analysis.abstract_provider import ANALYSIS_SCHEMA, AbstractProvider


class OllamaProvider(AbstractProvider):
    """Child class that asks a model served by Ollama (the fine-tuned lili-analyst by default) for each analysis."""

    def __init__(self, url: str, model: str, timeout_seconds: float) -> None:
        """Remember where Ollama runs, which model to use and how long to wait for one answer."""
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _generate(self, system_prompt: str, user_prompt: str) -> dict:
        """Ask the model for one analysis. The JSON schema in "format" makes Ollama answer in exactly that shape."""
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": ANALYSIS_SCHEMA,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.timeout_seconds,
        )
        # An HTTP error or an answer that is not valid JSON raises here, which sends the job back to the queue.
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
