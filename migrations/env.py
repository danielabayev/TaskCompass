"""Alembic environment. URL: the `sqlalchemy.url` option if a caller set it
(the tests do), otherwise the app database from .env."""

from alembic import context
from sqlalchemy import create_engine

from task_compass import config
from task_compass.models import Base

alembic_config = context.config
url = alembic_config.get_main_option("sqlalchemy.url") or config.database_url()


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
