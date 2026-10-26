"""Database engine and session helpers."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from task_compass import config

_engines: dict[str, object] = {}


def get_engine(url: str | None = None):
    url = url or config.database_url()
    if url not in _engines:
        _engines[url] = create_engine(url, future=True)
    return _engines[url]


def make_session_factory(url: str | None = None) -> sessionmaker:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker):
    """One unit of work: commit on success, roll back on error."""
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
