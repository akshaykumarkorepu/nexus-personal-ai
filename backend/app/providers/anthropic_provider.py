"""Anthropic Messages API adapter (streaming)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from ..config import Settings
from .base import ProviderError, ProviderEvent, TextDelta, ThinkingStarted, ToolCall, TurnComplete

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"
    supports_tools = True
    persists_replies = True

    def __init__(self, settings: Settings) -> None:
        self.model = settings.model
        self.effort = settings.effort
        self.max_tokens = settings.max_tokens
        self.refusal_fallback = settings.refusal_fallback
        api_key = (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        )
        token = (
            settings.anthropic_auth_token.get_secret_value()
            if settings.anthropic_auth_token
            else ""
        )
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or None,
            auth_token=None if api_key else token or None,
            base_url=settings.anthropic_base_url or None,
            timeout=settings.request_timeout_seconds,
            max_retries=2,
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if tools:
            params["tools"] = tools
        if self.refusal_fallback:
            # If a safety classifier declines, the API re-runs the request on
            # Anthropic's recommended fallback model inside the same call.
            params["fallbacks"] = "default"
            params["betas"] = [FALLBACK_BETA]

        try:
            async with self.client.beta.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type in ("thinking", "redacted_thinking"):
                            yield ThinkingStarted()
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield TextDelta(event.delta.text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError:
            raise ProviderError(
                "auth_failed",
                "Anthropic rejected the credentials. Check ANTHROPIC_API_KEY in backend/.env.",
                status=401,
            ) from None
        except anthropic.PermissionDeniedError as exc:
            raise ProviderError(
                "permission_denied", f"The API key cannot use this model: {exc.message}", status=403
            ) from None
        except anthropic.NotFoundError:
            raise ProviderError(
                "model_not_found",
                f"Model '{self.model}' was not found. Check NEXUS_MODEL in backend/.env.",
                status=404,
            ) from None
        except anthropic.RateLimitError:
            raise ProviderError(
                "rate_limited", "Rate limited by Anthropic. Wait a moment and retry.", status=429
            ) from None
        except anthropic.BadRequestError as exc:
            raise ProviderError(
                "bad_request", f"Anthropic rejected the request: {exc.message}", status=400
            ) from None
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderError(
                    "provider_unavailable",
                    f"Anthropic is unavailable or overloaded ({exc.status_code}). Retry shortly.",
                    status=exc.status_code,
                ) from None
            raise ProviderError(
                "provider_error", f"Anthropic API error: {exc.message}", status=exc.status_code
            ) from None
        except anthropic.APITimeoutError:
            raise ProviderError("timeout", "The request to Anthropic timed out.") from None
        except anthropic.APIConnectionError:
            raise ProviderError(
                "connection_failed", "Could not reach the Anthropic API. Check your connection."
            ) from None
        except ValueError:
            # The SDK raises ValueError for tool-input JSON it cannot parse at all.
            raise ProviderError(
                "malformed_output", "The model produced malformed tool input. Please retry."
            ) from None

        content = [block.to_dict(exclude_none=True) for block in final.content]
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in final.content
            if b.type == "tool_use"
        ]
        refusal = None
        if final.stop_reason == "refusal":
            details = getattr(final, "stop_details", None)
            refusal = getattr(details, "explanation", None) or "The model declined this request."
        usage = {
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "cache_read_input_tokens": final.usage.cache_read_input_tokens or 0,
        }
        yield TurnComplete(
            content=content,
            stop_reason=final.stop_reason,
            tool_calls=tool_calls,
            model=final.model,
            usage=usage,
            refusal_explanation=refusal,
        )
