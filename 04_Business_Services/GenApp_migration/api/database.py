"""
database.py
------------
Connection pooling for the FastAPI app. Uses the same PGHOST/PGPORT/
PGDATABASE/PGUSER/PGPASSWORD environment variable convention (and the
same genapp/postgres/CHANGE_ME_LOCAL_ONLY local-dev defaults) as the rest of this
project - see scripts/db_connect.py.

A psycopg2 ThreadedConnectionPool is used directly (no ORM) to stay
consistent with the rest of the codebase, which is deliberately plain
SQL throughout - the loaders, validator, and Streamlit apps all work
this way, so the API does too.
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

PG_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": os.environ.get("PGPORT", "5432"),
    "dbname": os.environ.get("PGDATABASE", "genapp"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "CHANGE_ME_LOCAL_ONLY"),
}

SCHEMA = os.environ.get("PGSCHEMA", "genapp")

_pool: ThreadedConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn, maxconn, **PG_CONFIG)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    """Borrow a connection from the pool, auto-return it on exit. Uses
    RealDictCursor so query results come back as {column: value} dicts,
    which map straight onto Pydantic response models."""
    if _pool is None:
        init_pool()
    conn = _pool.getconn()
    try:
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def get_db():
    """FastAPI dependency - yields a live connection for the duration of
    one request."""
    with get_conn() as conn:
        yield conn
