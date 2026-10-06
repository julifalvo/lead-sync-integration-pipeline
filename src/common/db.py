"""Thin psycopg connection helpers shared by the API and the worker."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


@contextmanager
def get_conn():
    settings = get_settings()
    conn = psycopg.connect(settings.postgres_dsn, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()
