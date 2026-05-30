"""Database backend configuration for the Streamlit app."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st


APP_DB_BACKEND_KEY = "APP_DB_BACKEND"
DEFAULT_DB_BACKEND = "sqlite"
VALID_DB_BACKENDS = {"sqlite", "postgres"}


def _read_streamlit_secret(key: str) -> Any | None:
    try:
        return st.secrets.get(key)
    except Exception:
        return None


def _normalize_backend(value: Any) -> str | None:
    if value is None:
        return None
    backend = str(value).strip().lower()
    return backend or None


def get_db_backend() -> str:
    backend = _normalize_backend(_read_streamlit_secret(APP_DB_BACKEND_KEY))
    if backend is None:
        backend = _normalize_backend(os.getenv(APP_DB_BACKEND_KEY))
    if backend is None:
        return DEFAULT_DB_BACKEND
    if backend not in VALID_DB_BACKENDS:
        allowed = ", ".join(sorted(VALID_DB_BACKENDS))
        raise ValueError(f"{APP_DB_BACKEND_KEY} 只能是 {allowed}，当前值为 {backend!r}。")
    return backend


def is_sqlite() -> bool:
    return get_db_backend() == "sqlite"


def is_postgres() -> bool:
    return get_db_backend() == "postgres"
