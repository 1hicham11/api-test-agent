"""Single point of contact with the LLM provider.

Groq is the default provider (via ``langchain-groq``). Switching providers
later only requires editing this module: replace :func:`get_llm` with any
LangChain chat model and everything else keeps working.

Reliability features for free-tier usage:

* exponential backoff + retry on rate limits (HTTP 429), max 3 retries;
* structured output via ``with_structured_output()`` with a fallback that
  extracts raw JSON from the model's text response if tool-calling fails.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "too many requests")


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce a usable answer after retries."""


def get_llm(temperature: float = 0.2) -> BaseChatModel:
    """Return the configured chat model (Groq by default).

    Raises:
        LLMError: if no API key is configured.
    """
    if not settings.groq_api_key:
        raise LLMError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add a key "
            "(free at https://console.groq.com)."
        )
    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=temperature,
    )


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _with_backoff(attempt: int) -> None:
    """Sleep with exponential backoff before retry ``attempt`` (1-based)."""
    delay = min(2.0 ** attempt, 20.0)
    logger.warning("LLM rate-limited, retrying in %.1fs (attempt %d)", delay, attempt)
    time.sleep(delay)


def extract_json(text: str) -> object:
    """Best-effort extraction of a JSON value from free-form model output.

    Handles plain JSON, ```json fenced blocks, and JSON embedded in prose.

    Raises:
        ValueError: if no JSON value can be decoded.
    """
    candidates: list[str] = [text.strip()]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidates.extend(block.strip() for block in fenced)
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON value found in model output")


def invoke_structured(system: str, user: str, schema: type[T]) -> T:
    """Call the LLM and parse its answer into ``schema``.

    Tries native structured output first; on failure falls back to asking for
    raw JSON and parsing it manually. Retries rate-limit errors with
    exponential backoff (max ``settings.llm_max_retries``).

    Raises:
        LLMError: if every strategy fails.
    """
    llm = get_llm()
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    last_error: Exception | None = None

    structured = llm.with_structured_output(schema)
    for attempt in range(1, settings.llm_max_retries + 1):
        try:
            result = structured.invoke(messages)
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
            raise ValueError(f"unexpected structured output type: {type(result)!r}")
        except Exception as exc:  # noqa: BLE001 - provider errors vary widely
            last_error = exc
            if _is_rate_limit(exc) and attempt < settings.llm_max_retries:
                _with_backoff(attempt)
                continue
            logger.warning("Structured output failed (%s), trying JSON fallback", exc)
            break

    # Fallback: plain completion, then extract and validate JSON ourselves.
    fallback_user = (
        f"{user}\n\nRespond with ONLY a JSON object matching this JSON Schema, "
        f"no prose:\n{json.dumps(schema.model_json_schema())}"
    )
    fallback_messages = [SystemMessage(content=system), HumanMessage(content=fallback_user)]
    for attempt in range(1, settings.llm_max_retries + 1):
        try:
            response = llm.invoke(fallback_messages)
            payload = extract_json(str(response.content))
            return schema.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if _is_rate_limit(exc) and attempt < settings.llm_max_retries:
                _with_backoff(attempt)
                continue
            break
    raise LLMError(f"LLM call failed after retries: {last_error}") from last_error
