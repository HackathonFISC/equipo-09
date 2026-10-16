"""Carga los seeds: `uv run python -m puente_api.db.seed [--reset]`.

Requiere `puente_api.db.session.SessionLocal` (sessionmaker) y las tablas ya creadas.
"""

import argparse
import logging

from puente_api.db.seed.loaders import seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga los datos semilla de Puente")
    parser.add_argument("--reset", action="store_true", help="borra las tablas semilla antes de cargar")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    from puente_api.db.session import SessionLocal

    with SessionLocal() as session:
        counts = seed_database(session, reset=args.reset)
        session.commit()
    print(counts or "Seeds ya cargados (usa --reset para recargar)")


if __name__ == "__main__":
    main()
