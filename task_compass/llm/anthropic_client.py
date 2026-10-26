"""The real model client (Claude through the Anthropic API)."""

import anthropic
import pydantic

from task_compass import config
from task_compass.llm.gateway import CallFailed, Completion, InvalidAnswer

# Thinking depth per call. The judge is a short classification-like task.
EFFORT = {"judge": "low", "ask": "medium", "propose": "medium"}


class AnthropicClient:
    def __init__(self, settings: config.Settings | None = None):
        settings = settings or config.Settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
        # The SDK retries overload (529), rate limits (429), 5xx and network
        # errors itself, with growing waits.
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_s,
        )

    def complete(self, *, purpose, model, system, user, schema) -> Completion:
        try:
            response = self._client.messages.parse(
                model=model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": EFFORT.get(purpose, "medium")},
            )
        except pydantic.ValidationError as exc:
            raise InvalidAnswer(f"schema mismatch: {exc.error_count()} errors") from exc
        except anthropic.APIError as exc:
            # Includes connection errors and timeouts after the SDK's retries.
            raise CallFailed(f"{type(exc).__name__}") from exc

        usage = response.usage
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            err = InvalidAnswer(f"no usable answer (stop_reason={response.stop_reason})")
            err.input_tokens, err.output_tokens = usage.input_tokens, usage.output_tokens
            raise err
        return Completion(response.parsed_output, usage.input_tokens, usage.output_tokens)
