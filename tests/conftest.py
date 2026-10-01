"""Shared test setup.

Database tests run in a SEPARATE database (football_test) on the same server, created
automatically, so running the tests can never touch the real pipeline data.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.db import DEFAULT_URL, init_schema

TEST_DB_NAME = "football_test"


def _test_url():
    url = make_url(os.getenv("DATABASE_URL", DEFAULT_URL))
    return url, url.set(database=TEST_DB_NAME)


@pytest.fixture(scope="session")
def test_engine():
    main_url, test_url = _test_url()
    if "neon.tech" in (main_url.host or "") or "supabase" in (main_url.host or ""):
        pytest.skip("Database tests only run against a local database")
    try:
        admin = create_engine(main_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        admin.dispose()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc.__class__.__name__}")

    engine = create_engine(test_url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS raw CASCADE; DROP SCHEMA IF EXISTS model CASCADE")
    init_schema(engine)
    yield engine
    engine.dispose()
