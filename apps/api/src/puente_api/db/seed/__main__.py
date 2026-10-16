"""Carga los seeds: `uv run python -m puente_api.db.seed [--reset]`.

Crea las tablas si faltan (`init_db`) y luego inserta los datos con `seed_database`.
"""

import argparse
import logging

from puente_api.db.seed.loaders import seed_database
from puente_api.db.session import SessionLocal, engine, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga los datos semilla de Puente")
    parser.add_argument(
        "--reset", action="store_true", help="borra las tablas semilla antes de cargar"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    init_db()
    with SessionLocal() as session:
        counts = seed_database(session, reset=args.reset)
        session.commit()
    print(counts or "Seeds ya cargados (usa --reset para recargar)")
    print(f"Base: {engine.url.render_as_string(hide_password=True)}")


if __name__ == "__main__":
    main()
