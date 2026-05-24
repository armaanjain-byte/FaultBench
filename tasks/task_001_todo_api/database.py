"""Database setup and session management for the TODO API."""
from __future__ import annotations

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

Base = declarative_base()


def _load_db_uri() -> str:
    """Load the database URI from config.yaml."""
    with open("config.yaml", "r") as fh:
        config = yaml.safe_load(fh)
    return config.get("database_uri", "sqlite:///todos.db")


engine = create_engine(_load_db_uri(), echo=False)
SessionLocal = scoped_session(sessionmaker(bind=engine))


def init_db() -> None:
    """Create all tables defined by the ORM models."""
    from models import Todo  # noqa: F401 — ensure model is registered
    Base.metadata.create_all(bind=engine)


def get_session():
    """Return a thread-local database session."""
    return SessionLocal()
