"""Motor y sesiones. SQLite en dev (`DATABASE_URL`), Postgres-compatible."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, inspect, text
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


def _add_missing_columns(bind: Engine) -> None:
    """`create_all` no altera tablas existentes: añade las columnas nuevas (nullable/default).

    Evita borrar `puente.db` cuando una rama agrega columnas. Solo cubre `ADD COLUMN` simple.
    """
    inspector = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or col.primary_key or col.foreign_keys:
                    continue
                ddl = col.type.compile(dialect=bind.dialect)
                default = ""
                if col.server_default is not None:
                    default = f" DEFAULT {col.server_default.arg!r}"
                stmt = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}{default}'
                conn.execute(text(stmt))


def init_db(bind: Engine = engine) -> None:
    """Crea las tablas que falten. Sin migraciones durante la hackathon."""
    Base.metadata.create_all(bind)
    _add_missing_columns(bind)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
