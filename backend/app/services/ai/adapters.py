"""Modular AI provider adapters with deterministic fallback chain."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)
NON_DIAGNOSTIC_NOTICE = (
    "This output is for research and engineering support only, not medical diagnosis "
    "or treatment guidance."
)
SYSTEM_GOVERNANCE_PREFIX = (
    "You are assisting with physiological signal QA. "
    "Do not provide medical diagnosis, treatment recommendations, or clinical claims. "
    "If asked for diagnosis, refuse and redirect to qualified clinical evaluation."
)


class ProviderCallError(RuntimeError):
    """Raised when provider invocation fails."""


class PromptValidationError(ValueError):
    """Raised when prompt violates governance constraints."""


class AIAdapter(Protocol):
    """Protocol for AI provider adapters."""

    name: str

    def available(self) -> bool:
        """Return whether provider is usable in current environment."""

    def generate(self, prompt: str, image_b64: str | None = None) -> str:
        """Return provider response for prompt (+ optional image)."""


def _extract_image_payload(image_b64: str) -> tuple[str, str]:
    """Return (mime_type, base64_data) from raw or data-url image payload."""
    if image_b64.startswith("data:"):
        header, data = image_b64.split(",", maxsplit=1)
        mime = header.split(";")[0].replace("data:", "") or "image/png"
        return mime, data
    return "image/png", image_b64


def _apply_governance(prompt: str) -> str:
    """Inject non-diagnostic governance instructions into provider prompt."""
    clean = prompt.strip()
    if not clean:
        raise PromptValidationError("prompt must not be empty")
    if len(clean) > settings.ai_max_prompt_chars:
        raise PromptValidationError(f"prompt exceeds {settings.ai_max_prompt_chars} characters")
    return f"{SYSTEM_GOVERNANCE_PREFIX}\n\nUser request:\n{clean}"


@dataclass
class GeminiAdapter:
    """Gemini adapter using official google-generativeai SDK."""

    name: str = "gemini"

    def available(self) -> bool:
        return bool(settings.gemini_api_key)

    def generate(self, prompt: str, image_b64: str | None = None) -> str:
        if not settings.gemini_api_key:
            raise ProviderCallError("Gemini API key not configured")
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ProviderCallError("google-generativeai package is not installed") from exc

        try:
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            if image_b64:
                mime_type, image_data = _extract_image_payload(image_b64)
                image_bytes = base64.b64decode(image_data)
                response = model.generate_content([prompt, {"mime_type": mime_type, "data": image_bytes}])
            else:
                response = model.generate_content(prompt)

            text = getattr(response, "text", None)
            if text:
                return str(text)
            raise ProviderCallError("Gemini returned empty response")
        except Exception as exc:  # pragma: no cover - network/provider behavior
            raise ProviderCallError(f"Gemini request failed: {exc}") from exc


@dataclass
class OpenAIAdapter:
    """OpenAI adapter using official openai SDK."""

    name: str = "openai"

    def available(self) -> bool:
        return bool(settings.openai_api_key)

    def generate(self, prompt: str, image_b64: str | None = None) -> str:
        if not settings.openai_api_key:
            raise ProviderCallError("OpenAI API key not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderCallError("openai package is not installed") from exc

        try:
            client = OpenAI(api_key=settings.openai_api_key)
            content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
            if image_b64:
                mime_type, image_data = _extract_image_payload(image_b64)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                    }
                )

            completion = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": content}],
                max_tokens=settings.ai_max_tokens,
            )
            text = completion.choices[0].message.content
            if text:
                return text
            raise ProviderCallError("OpenAI returned empty response")
        except Exception as exc:  # pragma: no cover - network/provider behavior
            raise ProviderCallError(f"OpenAI request failed: {exc}") from exc


@dataclass
class ClaudeAdapter:
    """Claude adapter using official anthropic SDK."""

    name: str = "claude"

    def available(self) -> bool:
        return bool(settings.claude_api_key)

    def generate(self, prompt: str, image_b64: str | None = None) -> str:
        if not settings.claude_api_key:
            raise ProviderCallError("Claude API key not configured")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ProviderCallError("anthropic package is not installed") from exc

        try:
            client = Anthropic(api_key=settings.claude_api_key)
            content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
            if image_b64:
                mime_type, image_data = _extract_image_payload(image_b64)
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_data,
                        },
                    }
                )

            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=settings.ai_max_tokens,
                messages=[{"role": "user", "content": content}],
            )

            text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
            text = "\n".join(text_blocks).strip()
            if text:
                return text
            raise ProviderCallError("Claude returned empty response")
        except Exception as exc:  # pragma: no cover - network/provider behavior
            raise ProviderCallError(f"Claude request failed: {exc}") from exc


class AIAssistantService:
    """Routes requests through adapter fallback sequence."""

    def __init__(self) -> None:
        self.providers: list[AIAdapter] = [GeminiAdapter(), OpenAIAdapter(), ClaudeAdapter()]

    def assist(self, prompt: str, image_b64: str | None = None) -> tuple[str, str, bool]:
        """Return (provider_name, response, fallback_used)."""
        governed_prompt = _apply_governance(prompt)
        allowed = {item.lower() for item in settings.ai_enabled_providers}
        configured = [provider for provider in self.providers if provider.available() and provider.name in allowed]
        if not configured:
            return "none", f"No AI provider configured. {NON_DIAGNOSTIC_NOTICE}", False

        errors: list[str] = []
        for idx, provider in enumerate(configured):
            try:
                response = provider.generate(governed_prompt, image_b64=image_b64)
                response_with_notice = f"{response.strip()}\n\nSafety notice: {NON_DIAGNOSTIC_NOTICE}".strip()
                return provider.name, response_with_notice, idx > 0
            except ProviderCallError as exc:
                logger.warning("AI provider failed: %s: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")

        joined = "; ".join(errors)
        return "none", f"All configured providers failed. Details: {joined}. {NON_DIAGNOSTIC_NOTICE}", False
