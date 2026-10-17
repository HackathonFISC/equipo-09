"""Checkpointer del grafo: permite pausar en `interrupt` (HITL) y reanudar tras la decisión.

Con una BD SQLite en archivo, los checkpoints viven en un archivo hermano
(`<db>-checkpoints.sqlite`) y sobreviven a reinicios de la API. Con SQLite en memoria (tests) o
cualquier otro motor se usa memoria del proceso; para Postgres basta cambiar esta función por
`langgraph-checkpoint-postgres` sin tocar el grafo.
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
    url = make_url(get_settings().database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        db = Path(url.database)
        path = db.with_name(f"{db.stem}-checkpoints.sqlite")
        return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
    return InMemorySaver()
