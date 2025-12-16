"""
AI Client for multi-model analysis.

Supports:
- Claude (Anthropic) - opus, sonnet
- OpenAI - gpt-4o, gpt-4-turbo
- Google Gemini - gemini-1.5-pro
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class AIClient(ABC):
    """Abstract base class for AI clients."""

    @abstractmethod
    def analyze(self, prompt: str, images: Optional[list[str]] = None) -> str:
        """Send prompt to AI and return response."""
        pass

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this model supports image analysis."""
        pass

    @property
    @abstractmethod
    def max_tokens(self) -> int:
        """Maximum context tokens for this model."""
        pass


class AnthropicClient(AIClient):
    """Claude client via Anthropic API."""

    MODELS = {
        "opus": "claude-opus-4-20250514",
        "sonnet": "claude-sonnet-4-20250514",
    }

    def __init__(self, model: str = "opus"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic: pip install anthropic")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = self.MODELS.get(model, model)
        self._model_name = model

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 200000  # Claude has 200k context

    def analyze(self, prompt: str, images: Optional[list[str]] = None) -> str:
        messages = []

        content = []
        # Add images if provided
        if images:
            import base64
            import httpx

            for img_url in images[:10]:  # Limit to 10 images
                try:
                    # Fetch image
                    resp = httpx.get(img_url, timeout=10)
                    if resp.status_code == 200:
                        img_data = base64.standard_b64encode(resp.content).decode("utf-8")
                        media_type = resp.headers.get("content-type", "image/jpeg")
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img_data,
                            }
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch image {img_url}: {e}")

        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=messages,
        )
        return response.content[0].text


class OpenAIClient(AIClient):
    """OpenAI GPT client."""

    MODELS = {
        "gpt4": "gpt-4o",
        "gpt4o": "gpt-4o",
        "gpt4-turbo": "gpt-4-turbo",
        "o1": "o1",
    }

    def __init__(self, model: str = "gpt4o"):
        try:
            import openai
        except ImportError:
            raise ImportError("Install openai: pip install openai")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        self.client = openai.OpenAI(api_key=api_key)
        self.model = self.MODELS.get(model, model)

    @property
    def supports_vision(self) -> bool:
        return "gpt-4" in self.model or "o1" in self.model

    @property
    def max_tokens(self) -> int:
        return 128000

    def analyze(self, prompt: str, images: Optional[list[str]] = None) -> str:
        content = []

        if images and self.supports_vision:
            for img_url in images[:10]:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })

        content.append({"type": "text", "text": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            max_tokens=8192,
        )
        return response.choices[0].message.content


class GeminiClient(AIClient):
    """Google Gemini client."""

    MODELS = {
        "gemini": "gemini-1.5-pro",
        "gemini-pro": "gemini-1.5-pro",
        "gemini-flash": "gemini-1.5-flash",
    }

    def __init__(self, model: str = "gemini"):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("Install google-generativeai: pip install google-generativeai")

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)
        model_name = self.MODELS.get(model, model)
        self.client = genai.GenerativeModel(model_name)

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 1000000  # Gemini 1.5 has 1M context

    def analyze(self, prompt: str, images: Optional[list[str]] = None) -> str:
        import httpx
        from PIL import Image
        from io import BytesIO

        parts = []

        if images:
            for img_url in images[:10]:
                try:
                    resp = httpx.get(img_url, timeout=10)
                    if resp.status_code == 200:
                        img = Image.open(BytesIO(resp.content))
                        parts.append(img)
                except Exception as e:
                    logger.warning(f"Failed to fetch image {img_url}: {e}")

        parts.append(prompt)

        response = self.client.generate_content(parts)
        return response.text


def get_ai_client(provider: str, model: Optional[str] = None) -> AIClient:
    """
    Get AI client for the specified provider.

    Args:
        provider: One of 'opus', 'sonnet', 'gpt4', 'gpt4o', 'gemini'
        model: Optional specific model override

    Returns:
        AIClient instance
    """
    provider = provider.lower()

    # Map common names to providers
    if provider in ("opus", "sonnet", "claude"):
        return AnthropicClient(model=model or provider)
    elif provider in ("gpt4", "gpt4o", "gpt4-turbo", "chatgpt", "openai", "o1"):
        return OpenAIClient(model=model or provider)
    elif provider in ("gemini", "gemini-pro", "gemini-flash", "google"):
        return GeminiClient(model=model or provider)
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            "Use: opus, sonnet, gpt4, gpt4o, gemini, gemini-flash"
        )
