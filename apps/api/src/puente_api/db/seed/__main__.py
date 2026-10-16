"""Carga los datos semilla: `uv run python -m puente_api.db.seed`.

Los loaders son de Sebastian (`puente_api.db.seed.load_all(session)`); este archivo solo los invoca.
"""

import sys

from puente_api.db.session import SessionLocal, engine, init_db


def main() -> int:
    try:
        from puente_api.db.seed import load_all  # type: ignore[attr-defined]
    except ImportError:
        print("Falta puente_api.db.seed.load_all(session): los loaders aún no existen.")
        return 1

    init_db()
    with SessionLocal() as session:
        load_all(session)
        session.commit()
    print(f"Seed cargado en {engine.url.render_as_string(hide_password=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
