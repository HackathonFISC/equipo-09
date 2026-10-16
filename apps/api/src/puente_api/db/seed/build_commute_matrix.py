"""Precomputa commute_matrix.csv a partir de locations.csv.

Uso: `uv run python -m puente_api.db.seed.build_commute_matrix`

Método (estimación documentada, no medición real):
- Distancia: haversine entre centroides × 1.35 (factor de sinuosidad vial).
- Modo: `metro` si origen y destino tienen estación de Metro (Líneas 1-2),
  `mixto` si solo uno, `bus` si ninguno.
- Tiempo puerta a puerta = espera + primeros 15 km a la velocidad efectiva del modo
  + el resto a 40 km/h (corredores y autopistas), referido a hora pico,
  más 15 min si el viaje cruza el Canal (Puente de las Américas / Centenario)
  y 10 min si alguno de los extremos es periurbano.
- Costo diario = 2 viajes × tarifa por viaje (ver TARIFAS).
- Mismo corregimiento: 8 min en bus, B/. 0.50 diario.
La matriz es completa (incluye la diagonal) y simétrica.
"""

import csv
import math
from pathlib import Path

SEED_DIR = Path(__file__).parent
ROAD_FACTOR = 1.35
SPEED_KMH = {"bus": 24.0, "metro": 33.0, "mixto": 26.0}
WAIT_MIN = {"bus": 12, "metro": 8, "mixto": 14}
URBAN_KM = 15.0  # tramo urbano a velocidad del modo; el resto va por corredor/autopista
HIGHWAY_KMH = 40.0
CANAL_PENALTY_MIN = 15
PERIURBAN_PENALTY_MIN = 10
# Tarifas por viaje (B/.): Metrobús urbano 0.25, Metro 0.35, transbordo bus+metro 0.60;
# bus interurbano Panamá Oeste <-> ciudad ~1.25; interno de Panamá Oeste ~0.60.
TARIFAS = {"bus": 0.25, "metro": 0.35, "mixto": 0.60}
FARE_CROSS_CANAL = 1.25
FARE_OESTE_INTERNAL = 0.60
FARE_PERIURBAN_EXTRA = 0.25


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def estimate(a: dict, b: dict) -> tuple[int, float, str]:
    """Devuelve (minutos, costo_diario, modo) para el par a→b."""
    if a["key"] == b["key"]:
        return 8, 0.50, "bus"
    km = haversine_km(float(a["lat"]), float(a["lng"]), float(b["lat"]), float(b["lng"])) * ROAD_FACTOR
    metro_a, metro_b = a["metro"] == "1", b["metro"] == "1"
    mode = "metro" if metro_a and metro_b else "mixto" if metro_a or metro_b else "bus"
    oeste_a, oeste_b = a["provincia"] == "Panamá Oeste", b["provincia"] == "Panamá Oeste"
    cross_canal = oeste_a != oeste_b
    periurban = "periurbana" in (a["zona"], b["zona"])

    urban_km = min(km, URBAN_KM)
    minutes = WAIT_MIN[mode] + urban_km / SPEED_KMH[mode] * 60 + (km - urban_km) / HIGHWAY_KMH * 60
    if cross_canal:
        minutes += CANAL_PENALTY_MIN
    if periurban:
        minutes += PERIURBAN_PENALTY_MIN

    if cross_canal:
        fare = FARE_CROSS_CANAL + (TARIFAS["metro"] if mode == "mixto" else 0)
    elif oeste_a and oeste_b:
        fare = FARE_OESTE_INTERNAL
    else:
        fare = TARIFAS[mode]
    if periurban:
        fare += FARE_PERIURBAN_EXTRA
    return round(minutes), round(2 * fare, 2), mode


def build(seed_dir: Path = SEED_DIR) -> list[dict]:
    with open(seed_dir / "locations.csv", encoding="utf-8", newline="") as f:
        locs = list(csv.DictReader(f))
    rows = []
    for a in locs:
        for b in locs:
            minutes, cost, mode = estimate(a, b)
            rows.append(
                {"origin": a["key"], "dest": b["key"], "minutes": minutes, "cost_daily": f"{cost:.2f}", "mode": mode}
            )
    return rows


def main() -> None:
    rows = build()
    with open(SEED_DIR / "commute_matrix.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["origin", "dest", "minutes", "cost_daily", "mode"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"commute_matrix.csv: {len(rows)} filas")


if __name__ == "__main__":
    main()
