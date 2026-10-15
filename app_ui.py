"""Streamlit-фронтенд для Social Post Generator."""

from __future__ import annotations

import html
import json
import os
from typing import Any, Final

import httpx
import streamlit as st
import streamlit.components.v1 as components

BACKEND_URL: Final[str] = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT: Final[float] = 120.0
CUSTOM_STYLE: Final[str] = "✏️ Свой стиль…"
STYLES: Final[list[str]] = [
    "Ироничный",
    "Деловой",
    "Провокационный",
    "Краткий (Twitter)",
    "Вдохновляющий",
    CUSTOM_STYLE,
]
LENGTHS: Final[dict[str, str]] = {
    "Короткий · 200–400": "short",
    "Средний · 500–900": "medium",
    "Длинный · 1200–2000": "long",
}
DEFAULT_LENGTH_LABEL: Final[str] = "Средний · 500–900"

CSS: Final[str] = """
<style>
.block-container { max-width: 760px; padding-top: 4.5rem; }
h1 { font-weight: 800; letter-spacing: -0.02em; }
.subtitle { color: #64748B; margin-top: -0.6rem; margin-bottom: 1.8rem; }
.stButton > button[kind="primary"] {
    border-radius: 12px; height: 3rem; font-weight: 600;
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%); border: none;
}
.stButton > button[kind="primary"]:hover { filter: brightness(1.08); }
.post-card {
    background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px;
    padding: 1.4rem 1.6rem; box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
    line-height: 1.65; font-size: 1.02rem; color: #0F172A;
}
.post-meta { color: #64748B; font-size: 0.85rem; margin: 0.6rem 0 0.2rem; }
</style>
"""


class BackendError(Exception):
    """Ошибка, полученная от бэкенда или при обращении к нему."""


def _error_detail(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return response.text or response.reason_phrase

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return "; ".join(str(item.get("msg", item)) for item in detail if isinstance(item, dict))
    return str(payload)


def request_post(url: str, style: str, length: str) -> str:
    try:
        response = httpx.post(
            f"{BACKEND_URL}/generate",
            json={"url": url, "style": style, "length": length},
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.ConnectError as exc:
        raise BackendError(
            f"Не удалось подключиться к бэкенду ({BACKEND_URL}). "
            "Запустите сервер: `uvicorn main:app --reload`"
        ) from exc
    except httpx.TimeoutException as exc:
        raise BackendError("Бэкенд не ответил вовремя. Попробуйте ещё раз.") from exc
    except httpx.HTTPError as exc:
        raise BackendError(f"Ошибка сети: {exc}") from exc

    if response.is_error:
        raise BackendError(f"Ошибка {response.status_code}: {_error_detail(response)}")

    post = response.json().get("post")
    if not isinstance(post, str) or not post:
        raise BackendError("Бэкенд вернул пустой ответ.")
    return post


def backend_is_alive() -> bool:
    try:
        return httpx.get(f"{BACKEND_URL}/health", timeout=2.0).is_success
    except httpx.HTTPError:
        return False


def copy_button(text: str) -> None:
    payload = json.dumps(text)
    components.html(
        f"""
        <button id="copy" style="
            width:100%; height:44px; border-radius:12px; cursor:pointer;
            border:1px solid #C7D2FE; background:#EEF2FF; color:#4338CA;
            font:600 15px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            📋 Скопировать в буфер
        </button>
        <script>
        const btn = document.getElementById("copy");
        const text = {payload};
        const done = (ok) => {{
            btn.textContent = ok ? "✅ Скопировано" : "⚠️ Не удалось скопировать";
            setTimeout(() => btn.textContent = "📋 Скопировать в буфер", 2000);
        }};
        btn.onclick = async () => {{
            try {{ await navigator.clipboard.writeText(text); done(true); }}
            catch (e) {{
                const ta = document.createElement("textarea");
                ta.value = text; document.body.appendChild(ta); ta.select();
                done(document.execCommand("copy")); ta.remove();
            }}
        }};
        </script>
        """,
        height=52,
    )


def main() -> None:
    st.set_page_config(page_title="Social Post AI Generator", page_icon="🤖", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)

    st.title("🤖 Social Post AI Generator")
    st.markdown(
        '<p class="subtitle">Вставьте ссылку на статью — получите готовый пост для соцсетей.</p>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("Бэкенд")
        st.caption(BACKEND_URL)
        if backend_is_alive():
            st.success("Сервер доступен", icon="🟢")
        else:
            st.error("Сервер недоступен", icon="🔴")
            st.code("uvicorn main:app --reload", language="bash")

    url = st.text_input("URL статьи", placeholder="https://example.com/article")

    selected = st.selectbox("Стиль поста", STYLES, index=0)
    style = selected
    if selected == CUSTOM_STYLE:
        style = st.text_input(
            "Ваш стиль", placeholder="Например: дружелюбный, с юмором для IT-аудитории"
        ).strip()

    length_label = (
        st.segmented_control(
            "Размер поста",
            list(LENGTHS),
            default=DEFAULT_LENGTH_LABEL,
            help="Примерное количество символов",
        )
        or DEFAULT_LENGTH_LABEL
    )

    if st.button("Сгенерировать пост", type="primary", use_container_width=True):
        if not url.strip():
            st.error("Введите URL статьи.")
        elif not style:
            st.error("Опишите свой стиль или выберите стиль из списка.")
        else:
            with st.spinner("Читаю статью и пишу пост…"):
                try:
                    st.session_state["post"] = request_post(
                        url.strip(), style, LENGTHS[length_label]
                    )
                    st.session_state["post_style"] = style
                    st.session_state["post_length"] = length_label.split(" · ")[0]
                except BackendError as exc:
                    st.session_state.pop("post", None)
                    st.error(str(exc), icon="🚫")

    post: str | None = st.session_state.get("post")
    if post:
        st.divider()
        st.subheader("Готовый пост")
        post_html = html.escape(post).replace("\n", "<br>")
        st.markdown(f'<div class="post-card">{post_html}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="post-meta">Стиль: {html.escape(st.session_state.get("post_style", ""))}'
            f' · Размер: {st.session_state.get("post_length", "")}'
            f" · {len(post)} символов</p>",
            unsafe_allow_html=True,
        )
        copy_button(post)


main()
