"""Motor y sesiones. SQLite en dev (`DATABASE_URL`), Postgres-compatible."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from puente_api.config import get_settings
from puente_api.db.models import Base


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_conn, _record):  # SQLite ignora FKs salvo que se activen.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind: Engine = engine) -> None:
    """Crea las tablas que falten. Sin migraciones durante la hackathon."""
    Base.metadata.create_all(bind)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
