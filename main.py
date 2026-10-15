"""FastAPI-бэкенд генератора постов."""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from agent import DEFAULT_LENGTH, DEFAULT_STYLE, PostLength, ScrapingError, SocialPostAgent
from openai_module import OpenAIClientError

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Social Post Generator",
    description="Генерация постов для соцсетей по ссылке на статью.",
    version="1.0.0",
)


class GenerateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, examples=["https://example.com/article"])
    style: str = Field(default=DEFAULT_STYLE, min_length=1, max_length=100)
    length: PostLength = DEFAULT_LENGTH


class GenerateResponse(BaseModel):
    url: str
    style: str
    length: PostLength
    post: str


class ErrorResponse(BaseModel):
    detail: str


@lru_cache(maxsize=1)
def get_agent() -> SocialPostAgent:
    return SocialPostAgent()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/generate",
    response_model=GenerateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Некорректный URL или страницу не удалось разобрать"},
        500: {"model": ErrorResponse, "description": "Сервер не настроен (нет ключа API)"},
        502: {"model": ErrorResponse, "description": "Ошибка OpenAI/ProxyAPI"},
    },
)
async def generate(request: GenerateRequest) -> GenerateResponse:
    try:
        agent = get_agent()
    except OpenAIClientError as exc:
        logger.error("Ошибка конфигурации: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc

    try:
        post = await agent.acreate_post(request.url, style=request.style, length=request.length)
    except (ValueError, ScrapingError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except OpenAIClientError as exc:
        logger.error("Ошибка генерации: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return GenerateResponse(
        url=request.url, style=request.style, length=request.length, post=post
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
