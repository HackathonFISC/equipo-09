"""Checkpointer del grafo: permite pausar en `interrupt` (HITL) y reanudar tras la decisión.

Con una BD SQLite en archivo, los checkpoints viven en un archivo hermano
(`<db>-checkpoints.sqlite`) y sobreviven a reinicios de la API. `CHECKPOINT_PATH` fija ese
archivo de forma explícita (en Docker, con Postgres, va en un volumen). Sin él, con SQLite en
memoria (tests) o cualquier otro motor se usa memoria del proceso.
"""

import sqlite3
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy.engine import make_url

from puente_api.config import get_settings


@lru_cache
def get_checkpointer() -> BaseCheckpointSaver:
    settings = get_settings()
    if settings.checkpoint_path:  # p. ej. Docker con Postgres: /data/checkpoints.sqlite
        path = Path(settings.checkpoint_path)
    else:
        url = make_url(settings.database_url)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            return InMemorySaver()
        db = Path(url.database)
        path = db.with_name(f"{db.stem}-checkpoints.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
