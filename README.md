# Social Post Generator

Генерирует пост для соцсетей по ссылке на статью: скачивает страницу (httpx + BeautifulSoup) и пишет пост через OpenAI (`gpt-4o-mini`) с помощью [ProxyAPI](https://proxyapi.ru).

## Требования

- Python 3.10+
- Ключ ProxyAPI

## Установка

```bash
cd social_post_generator
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

Отредактируйте `.env`:

```env
PROXYAPI_KEY=sk-...ваш_ключ...
PROXYAPI_BASE_URL=https://api.proxyapi.ru/openai/v1
```

## Запуск веб-сервера

```bash
uvicorn main:app --reload
# или: python main.py
```

Документация API (Swagger): http://127.0.0.1:8000/docs

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article", "style": "деловой", "length": "short"}'
```

`length` — размер поста: `short` (200–400 символов), `medium` (500–900, по умолчанию), `long` (1200–2000).

Ответ: `{"url": "...", "style": "...", "length": "...", "post": "..."}`

| Код | Когда |
|-----|-------|
| 200 | Пост сгенерирован |
| 400 | Некорректный URL, страница недоступна или не содержит текста |
| 422 | Неверный формат JSON (нет поля `url`) |
| 500 | Сервер не настроен: не задан `PROXYAPI_KEY` |
| 502 | Ошибка OpenAI/ProxyAPI (ключ, баланс, таймаут) |

Ошибки возвращаются в виде `{"detail": "сообщение"}`.

## Веб-интерфейс (Streamlit)

Запустите бэкенд (см. выше), затем во втором терминале:

```bash
streamlit run app_ui.py
```

Интерфейс откроется на http://localhost:8501. Адрес бэкенда можно поменять переменной окружения `BACKEND_URL` (по умолчанию `http://127.0.0.1:8000`).

## Docker

Ключ должен быть в `.env`. Затем:

```bash
docker compose up --build
```

- API: http://127.0.0.1:8000/docs
- Интерфейс: http://localhost:8501

Фронтенд ждёт, пока бэкенд ответит на `/health`. Внутри сети Compose он ходит на `http://backend:8000`. Остановить: `docker compose down`.

## Запуск из консоли

```bash
python agent.py https://example.com/article
python agent.py https://example.com/article --style "деловой" --length long -v
```

Из кода:

```python
from agent import SocialPostAgent

agent = SocialPostAgent()
print(agent.create_post("https://example.com/article", style="ироничный"))
# в асинхронном коде: await agent.acreate_post(url, style="ироничный")
```

## Структура

| Файл | Назначение |
|------|------------|
| `openai_module.py` | `OpenAIClient` — обёртка над OpenAI SDK, читает ключ и URL из `.env` |
| `agent.py` | `SocialPostAgent` — парсинг страницы и генерация поста (sync и async), CLI |
| `main.py` | FastAPI-бэкенд, эндпоинт `POST /generate` |
| `app_ui.py` | Streamlit-фронтенд |
| `.streamlit/config.toml` | Тема интерфейса |
| `requirements.txt` | Зависимости |
| `.env` | Ключ и URL прокси (не коммитить) |
| `Dockerfile.backend` | Образ FastAPI / uvicorn |
| `Dockerfile.frontend` | Образ Streamlit |
| `docker-compose.yml` | Запуск обоих сервисов |
| `.dockerignore` | Исключает `.venv`, `.git`, `.env`, логи |

## Ошибки

- `ValueError` — некорректный URL или пустой промпт.
- `ScrapingError` — страница недоступна, не HTML или содержит слишком мало текста.
- `OpenAIClientError` — не задан ключ, неверный ключ, лимит/баланс, сетевые ошибки API.
