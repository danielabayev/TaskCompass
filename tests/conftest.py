"""Shared fixtures.

Database tests run against a separate database (<POSTGRES_DB>_test), migrated
with Alembic once per run. Each test starts with empty tables except the
seeded categories.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from task_compass import config
from task_compass.db import get_engine, make_session_factory

DATA_TABLES = ["llm_calls", "retros", "checkpoints", "interview_turns", "tasks"]


@pytest.fixture(scope="session")
def db_url():
    url = config.database_url(test=True)
    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
def session_factory(db_url):
    engine = get_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
        conn.execute(text("UPDATE categories SET active = true"))
    return make_session_factory(db_url)


@pytest.fixture
def session(session_factory):
    s = session_factory()
    yield s
    s.rollback()
    s.close()
