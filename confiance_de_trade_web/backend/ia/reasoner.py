"""Thin wrapper around external reasoning providers."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import aiohttp

LOGGER = logging.getLogger(__name__)


class ReasonerClient:
    """Async client for LLM-based classification."""

    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider = provider or os.getenv("CT_REASONER_PROVIDER", "openai")
        self._session: Optional[aiohttp.ClientSession] = None

    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def classify_event(self, prompt: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the configured provider.

        The implementation deliberately returns ``None`` when no API key is configured to keep
        the pipeline offline-friendly. Integrations should override this method once credentials
        are available.
        """

        if not self._has_credentials():
            LOGGER.debug("No credentials configured for provider %s", self.provider)
            return None

        # Placeholder HTTP call illustrating structure. Providers differ wildly so this is
        # intentionally conservative and designed to be replaced by production integrations.
        session = await self.ensure_session()
        try:
            if self.provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
                body = {
                    "model": os.getenv("CT_OPENAI_MODEL", "gpt-4.1-mini"),
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                    "temperature": 0,
                }
                async with session.post(url, headers=headers, json=body) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        LOGGER.warning("OpenAI response missing choices: %s", data)
                        return None

                    message = choices[0].get("message") or {}
                    tool_output = message.get("tool_calls") or []
                    if tool_output:
                        arguments = tool_output[0].get("function", {}).get("arguments")
                        if arguments:
                            try:
                                return json.loads(arguments)
                            except json.JSONDecodeError:
                                LOGGER.exception("Invalid JSON in tool call: %s", arguments)
                                return None
                    content = message.get("content")
                    if content:
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            LOGGER.exception("Invalid JSON content: %s", content)
                            return None
                    LOGGER.warning("OpenAI response missing tool output and content: %s", data)
                    return None
            LOGGER.warning("Provider %s not implemented", self.provider)
        except Exception as exc:  # pragma: no cover - network failures are logged
            LOGGER.exception("Reasoner call failed: %s", exc)
        return None

    @staticmethod
    def build_prompt(instruction: str, schema: str) -> str:
        """Return a reusable prompt for tool-based classification."""
        return f"{instruction.strip()}\n\nSchema JSON attendu:\n{schema.strip()}"

    def _has_credentials(self) -> bool:
        if self.provider == "openai":
            return bool(os.getenv("OPENAI_API_KEY"))
        if self.provider == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        if self.provider == "google":
            return bool(os.getenv("GOOGLE_API_KEY"))
        return False
