"""Обёртка над OpenAI SDK для работы через ProxyAPI."""

from __future__ import annotations

import logging
import os
from typing import Final

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

logger = logging.getLogger(__name__)

DEFAULT_MODEL: Final[str] = "gpt-4o-mini"
PLACEHOLDER_KEY: Final[str] = "your_key_here"


class OpenAIClientError(Exception):
    """Ошибка конфигурации или вызова OpenAI API."""


class OpenAIClient:
    """Клиент для генерации текста через OpenAI-совместимый прокси."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        load_dotenv()

        api_key = os.getenv("PROXYAPI_KEY", "").strip()
        base_url = os.getenv("PROXYAPI_BASE_URL", "").strip()

        if not api_key or api_key == PLACEHOLDER_KEY:
            raise OpenAIClientError(
                "Не задан PROXYAPI_KEY. Укажите ключ в файле .env."
            )
        if not base_url:
            raise OpenAIClientError(
                "Не задан PROXYAPI_BASE_URL. Укажите URL прокси в файле .env."
            )

        self.model: str = model
        self._client: OpenAI = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._async_client: AsyncOpenAI = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 800,
    ) -> str:
        """Генерирует текст по промпту и возвращает ответ модели."""
        messages = _build_messages(prompt, system_prompt)
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIError as exc:
            raise _map_api_error(exc) from exc
        return self._extract_content(response)

    async def agenerate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 800,
    ) -> str:
        """Асинхронная версия generate_text."""
        messages = _build_messages(prompt, system_prompt)
        try:
            response = await self._async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIError as exc:
            raise _map_api_error(exc) from exc
        return self._extract_content(response)

    def _extract_content(self, response: ChatCompletion) -> str:
        if not response.choices:
            raise OpenAIClientError("API вернул пустой список вариантов ответа.")

        content = response.choices[0].message.content
        if not content:
            raise OpenAIClientError("API вернул пустой ответ.")

        logger.debug("Сгенерировано %d символов моделью %s", len(content), self.model)
        return content.strip()


def _build_messages(
    prompt: str, system_prompt: str | None
) -> list[ChatCompletionMessageParam]:
    if not prompt.strip():
        raise ValueError("Промпт не может быть пустым.")

    messages: list[ChatCompletionMessageParam] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return messages


def _map_api_error(exc: APIError) -> OpenAIClientError:
    if isinstance(exc, AuthenticationError):
        return OpenAIClientError("Неверный API-ключ ProxyAPI.")
    if isinstance(exc, RateLimitError):
        return OpenAIClientError(
            "Превышен лимит запросов или недостаточно средств на балансе."
        )
    if isinstance(exc, APITimeoutError):
        return OpenAIClientError("Превышено время ожидания ответа API.")
    if isinstance(exc, APIConnectionError):
        return OpenAIClientError(
            "Не удалось подключиться к API. Проверьте PROXYAPI_BASE_URL и сеть."
        )
    return OpenAIClientError(f"Ошибка OpenAI API: {exc}")
