# Datos semilla (H1)

Datos de demo para Puente. Los archivos referencian entidades por una `key` legible
(`barrio-balboa`, `manejo-de-caja`); el loader deriva el UUID con
`seed_uuid(tabla, key)` (uuid5 determinista), así los IDs son estables entre cargas.

| Archivo | Tabla(s) del doc 05 | Filas | Real / sintético |
|---|---|---|---|
| `locations.csv` | `location` | 50 corregimientos | Real (nombres); coordenadas aproximadas |
| `commute_matrix.csv` | `commute_matrix` | 2 500 (50 × 50) | Estimación calculada (ver método) |
| `skills.csv` | `skill` | 150 | Curado a mano, inspirado en ESCO |
| `companies.json` | `company` | 15 | Sintético (empresas ficticias, dominio `.example`) |
| `postings.json` | `job_posting`, `posting_requirement` | 25 ofertas, 84 requisitos | Sintético |
| `discrimination_labels.json` | — (etiquetas para evals) | 25 | Etiquetado a mano |
| `courses.json` | `training_center`, `course`, `course_skill`, `course_session` | 4 centros, 12 cursos, 21 sesiones | Sintético inspirado en INADEH |
| `youth.json` | `youth`, `profile_skill` | 40 jóvenes, 191 habilidades | Sintético |

`build_commute_matrix.py` y `build_youth.py` generan los dos archivos derivados. Los tests
comprueban que los archivos versionados coinciden con lo que generan los scripts; si editas
un script, vuelve a generar:

```bash
cd apps/api
uv run python -m puente_api.db.seed.build_commute_matrix
uv run python -m puente_api.db.seed.build_youth
```

## Fuentes y tratamiento (doc 02 §8)

- **Corregimientos.** Los nombres, distritos y provincias vienen de la división político-administrativa
  oficial de Panamá (INEC). Es un subconjunto de 50 corregimientos: los 26 del distrito de Panamá, los
  9 de San Miguelito, los 8 de Arraiján y 7 urbanos de La Chorrera. El doc 05 pedía unos 60; con 50
  caben las zonas del demo y la matriz sigue siendo pequeña. **Lat/lng son centroides aproximados**
  (precisión ~1 km), puestos a mano para estimar distancias. No sirven para cartografía. Las columnas
  `metro` (hay estación de Metro L1/L2 en el corregimiento o junto a él) y `zona` (urbana/periurbana)
  son auxiliares de la matriz y no se cargan a la BD.
- **Matriz de traslado.** Estimación, no medición. El método está en el docstring de
  `build_commute_matrix.py`: distancia haversine × 1,35; modo bus/metro/mixto según el acceso al
  Metro; velocidades efectivas de hora pico; penalidad por cruzar el Canal y por zona periurbana;
  tarifas de referencia (Metrobús B/. 0,25, Metro B/. 0,35, interurbano Panamá Oeste ~B/. 1,25).
  Es completa (incluye la diagonal) y simétrica. Línea 3 del Metro no se modela.
- **Habilidades (ESCO-lite).** 150 habilidades en español con grupo y alias, pensadas para empleos de
  entrada en Panamá. Están inspiradas en el pilar de habilidades de ESCO, pero **`esco_uri` queda vacío**:
  falta mapear cada fila a su URI oficial en el buscador ESCO (tarea pendiente). Los alias sirven al
  agente de Mercado para el mapeo por diccionario.
- **Ofertas.** **Sintéticas** (`is_synthetic: true`, campo `source`). Están redactadas siguiendo el
  formato de los anuncios de portales públicos de empleo y volantes en Panamá. Las empresas son
  ficticias. El doc 05 pide "25 ofertas reales normalizadas": cuando se recolecten, se reemplazan
  aquí guardando el origen en `source` y anonimizando la empresa si hace falta.
- **Cursos.** INADEH tiene sedes en los distritos usados, pero los nombres de sede son aproximados.
  Los títulos siguen la oferta típica de INADEH. Horarios, fechas, cupos y costos (materiales) son
  **sintéticos** (`is_synthetic: true`). La mayoría de los cursos INADEH son gratuitos.
- **Jóvenes.** Los 40 son **sintéticos** (`is_synthetic: true`). Ana es la persona del PRD (21 años,
  Barrio Balboa, La Chorrera; estudia de noche; transporte ≤ B/. 4; sin CV). Las otras 39 se generan con
  semilla fija a partir de 14 arquetipos. Panamá Oeste está sobrerrepresentado para que Ana tenga pares
  comparables, y el género está balanceado para el auditor contrafactual. Cada habilidad trae
  `evidence`, y `cv_raw_text` se arma con esas frases.

## Ofertas discriminatorias (para guardrail y evals)

`discrimination_labels.json` tiene una etiqueta por oferta:
`{posting, discriminatory, findings: [{kind, text}], notes?}`. `text` es el fragmento literal de
`raw_input` (los tests lo verifican). `kind` ∈ `edad`, `genero`, `apariencia`, `foto`,
`estado_civil`, `embarazo`, `residencia`, `nacionalidad`.

- 6 ofertas discriminatorias (`status: borrador`, a la espera del auditor):
  `cajeras-supermercado-arraijan`, `ayudante-bodega-tocumen`, `agente-cobros-call-center`,
  `recepcionista-oficina-soltera`, `mesera-restaurante`, `vendedor-tienda-ropa`.
- 3 controles de precisión: requisitos legítimos que parecen sensibles (carné de manipulador,
  "mayores de 18 años" en construcción, licencia de conducir para reparto). Están marcados con
  `notes` y `discriminatory: false`.

## Carga

```python
from puente_api.db.seed import seed_database

counts = seed_database(session)  # idempotente; reset=True para recargar
session.commit()
```

O desde la terminal: `uv run python -m puente_api.db.seed [--reset]` (requiere
`puente_api.db.session.SessionLocal`).
