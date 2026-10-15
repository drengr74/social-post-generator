"""Агент для генерации постов в соцсети на основе содержимого веб-страницы."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Final, Literal, NamedTuple, get_args
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from openai_module import OpenAIClient, OpenAIClientError

logger = logging.getLogger(__name__)

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NOISE_TAGS: Final[tuple[str, ...]] = (
    "script", "style", "noscript", "header", "footer", "nav", "aside", "form", "svg", "iframe",
)
NOISE_SELECTORS: Final[str] = (
    '[role="navigation"], [role="banner"], [role="contentinfo"], [role="search"], '
    '[aria-hidden="true"]'
)
MIN_TEXT_LENGTH: Final[int] = 100
DEFAULT_STYLE: Final[str] = "ироничный"

PostLength = Literal["short", "medium", "long"]


class LengthSpec(NamedTuple):
    chars: str
    emojis: str
    hashtags: str
    max_tokens: int


LENGTH_SPECS: Final[dict[PostLength, LengthSpec]] = {
    "short": LengthSpec("200–400", "1–2", "2–3", 400),
    "medium": LengthSpec("500–900", "2–4", "3–5", 800),
    "long": LengthSpec("1200–2000", "3–6", "4–6", 1600),
}
DEFAULT_LENGTH: Final[PostLength] = "medium"

SYSTEM_PROMPT: Final[str] = (
    "Ты — опытный SMM-специалист. Пишешь короткие, цепляющие посты для соцсетей "
    "на русском языке. Не выдумываешь факты, опираешься только на исходный текст."
)


class ScrapingError(Exception):
    """Ошибка загрузки или разбора веб-страницы."""


class SocialPostAgent:
    """Извлекает текст со страницы и генерирует по нему пост."""

    def __init__(
        self,
        llm_client: OpenAIClient | None = None,
        timeout: float = 15.0,
        max_chars: int = 6000,
    ) -> None:
        self.llm: OpenAIClient = llm_client or OpenAIClient()
        self.timeout: float = timeout
        self.max_chars: int = max_chars

    @staticmethod
    def _validate_url(url: str) -> str:
        url = url.strip()
        if "://" not in url:
            url = f"https://{url.removeprefix('//')}"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Некорректный URL: {url!r}")
        return url

    def _client_options(self) -> dict[str, Any]:
        return {
            "timeout": self.timeout,
            "follow_redirects": True,
            "headers": {"User-Agent": USER_AGENT},
        }

    def extract_text(self, url: str) -> str:
        """Загружает страницу и возвращает очищенный основной текст."""
        url = self._validate_url(url)
        try:
            with httpx.Client(**self._client_options()) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _map_http_error(exc, url) from exc
        return self._parse_html(response, url)

    async def aextract_text(self, url: str) -> str:
        """Асинхронная версия extract_text."""
        url = self._validate_url(url)
        try:
            async with httpx.AsyncClient(**self._client_options()) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _map_http_error(exc, url) from exc
        return self._parse_html(response, url)

    def _parse_html(self, response: httpx.Response, url: str) -> str:
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            raise ScrapingError(f"Страница не является HTML (Content-Type: {content_type})")

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(NOISE_TAGS):
            tag.decompose()
        for tag in soup.select(NOISE_SELECTORS):
            tag.decompose()

        root = soup.find("article") or soup.find("main") or soup.body or soup
        title = soup.title.get_text(strip=True) if soup.title else ""

        lines = [line.strip() for line in root.get_text(separator="\n").splitlines()]
        text = "\n".join(line for line in lines if line)

        if title and not text.startswith(title):
            text = f"{title}\n\n{text}"

        if len(text) < MIN_TEXT_LENGTH:
            raise ScrapingError("Не удалось извлечь достаточно текста со страницы.")

        logger.debug("Извлечено %d символов с %s", len(text), url)
        return text[: self.max_chars]

    def create_post(
        self, url: str, style: str = DEFAULT_STYLE, length: PostLength = DEFAULT_LENGTH
    ) -> str:
        """Извлекает текст по URL и генерирует пост в заданном стиле и размере."""
        text = self.extract_text(url)
        return self.llm.generate_text(
            _build_prompt(url, style, length, text),
            system_prompt=SYSTEM_PROMPT,
            max_tokens=LENGTH_SPECS[length].max_tokens,
        )

    async def acreate_post(
        self, url: str, style: str = DEFAULT_STYLE, length: PostLength = DEFAULT_LENGTH
    ) -> str:
        """Асинхронная версия create_post."""
        text = await self.aextract_text(url)
        return await self.llm.agenerate_text(
            _build_prompt(url, style, length, text),
            system_prompt=SYSTEM_PROMPT,
            max_tokens=LENGTH_SPECS[length].max_tokens,
        )


def _build_prompt(url: str, style: str, length: PostLength, text: str) -> str:
    spec = LENGTH_SPECS[length]
    return (
        f"Напиши пост для соцсети в стиле: {style}.\n"
        f"Требования: строго {spec.chars} символов, яркий первый абзац, "
        f"{spec.emojis} уместных эмодзи, {spec.hashtags} хэштегов в конце, "
        "ссылка на источник в последней строке.\n"
        "Пиши обычным текстом без Markdown-разметки; ссылку указывай как голый URL.\n\n"
        f"Источник: {url}\n\n"
        f"Текст статьи:\n{text}"
    )


def _map_http_error(exc: httpx.HTTPError, url: str) -> ScrapingError:
    if isinstance(exc, httpx.TimeoutException):
        return ScrapingError(f"Таймаут при загрузке {url}")
    if isinstance(exc, httpx.HTTPStatusError):
        return ScrapingError(f"Сервер вернул статус {exc.response.status_code} для {url}")
    return ScrapingError(f"Сетевая ошибка при загрузке {url}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Генератор постов для соцсетей по URL.")
    parser.add_argument("url", help="Ссылка на статью")
    parser.add_argument("--style", default=DEFAULT_STYLE, help="Стиль поста")
    parser.add_argument(
        "--length", default=DEFAULT_LENGTH, choices=get_args(PostLength), help="Размер поста"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Подробные логи")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    try:
        agent = SocialPostAgent()
        print(agent.create_post(args.url, style=args.style, length=args.length))
    except (ValueError, ScrapingError, OpenAIClientError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
