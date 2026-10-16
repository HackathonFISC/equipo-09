"""Genera youth.json: 40 perfiles sintéticos (Ana + 39 generados con semilla fija).

Uso: `uv run python -m puente_api.db.seed.build_youth`

Todos los perfiles son sintéticos (`is_synthetic: true`). Cada habilidad trae `evidence`
textual y el `cv_raw_text` se arma con esas mismas frases, para que el agente de Perfil
pueda re-extraerlas y los evals comparen contra estas etiquetas.
"""

import csv
import json
import random
from pathlib import Path

SEED_DIR = Path(__file__).parent
RNG_SEED = 2026
N_YOUTH = 40

LV = ["lun", "mar", "mie", "jue", "vie"]

ANA = {
    "key": "ana",
    "display_name": "Ana",
    "birth_year": 2005,
    "gender": "femenino",
    "location": "barrio-balboa",
    "max_commute_min": 60,
    "transport_budget_daily": 4.0,
    "min_salary": 600,
    "studying": True,
    "availability": [{"day": d, "start": "07:00", "end": "16:00"} for d in LV + ["sab"]],
    "cv_raw_text": None,
    "is_synthetic": True,
    "persona": "demo",
    "skills": [
        {
            "skill": "manejo-de-caja",
            "level": 3,
            "source": "entrevista",
            "evidence": "Durante 3 años cobré en la caja de la fonda de mi familia.",
        },
        {
            "skill": "cuadre-de-caja",
            "level": 2,
            "source": "entrevista",
            "evidence": "Al final del día contaba el dinero y cuadraba la caja con mi mamá.",
        },
        {
            "skill": "control-de-inventario",
            "level": 2,
            "source": "entrevista",
            "evidence": "Llevaba en un cuaderno lo que entraba y salía de la despensa y avisaba qué comprar.",
        },
        {
            "skill": "atencion-al-cliente",
            "level": 3,
            "source": "entrevista",
            "evidence": "Atendía a los clientes de la fonda en la hora del almuerzo, muchos eran fijos.",
        },
        {
            "skill": "atencion-de-fonda",
            "level": 3,
            "source": "entrevista",
            "evidence": "Ayudé 3 años en la fonda familiar.",
        },
        {
            "skill": "calculo-basico",
            "level": 2,
            "source": "entrevista",
            "evidence": "Sacaba las cuentas y el vuelto sin calculadora.",
        },
    ],
}

# Arquetipos: (habilidad, nivel, frase de evidencia en primera persona)
ARCHETYPES = {
    "comercio": [
        ("ventas-al-detalle", 2, "Trabajé en ventas en una tienda de ropa los fines de semana."),
        ("manejo-de-caja", 2, "Cubría la caja cuando la cajera salía a almorzar."),
        ("reposicion-de-mercancia", 2, "Reponía mercancía en los anaqueles y revisaba fechas de vencimiento."),
        ("atencion-al-cliente", 2, "Atendía clientes y les ayudaba a encontrar productos."),
        ("punto-de-venta-pos", 1, "Usé el sistema POS de la tienda para cobrar."),
    ],
    "call_center": [
        ("call-center", 2, "Estuve 6 meses en un call center atendiendo llamadas de clientes."),
        ("ingles-conversacional", 2, "Hablo inglés conversacional; atendía la línea en inglés."),
        ("manejo-de-quejas", 2, "Resolvía reclamos de facturación por teléfono."),
        ("digitacion-de-datos", 2, "Registraba cada llamada en el sistema CRM."),
    ],
    "logistica": [
        ("carga-y-descarga", 2, "Trabajé cargando y descargando camiones en una distribuidora."),
        ("picking-y-packing", 2, "Preparaba pedidos y los empacaba para despacho."),
        ("escaner-de-codigos", 1, "Usaba el escáner para registrar la mercancía."),
        ("inventario-en-bodega", 1, "Ayudaba en los conteos de inventario de la bodega."),
    ],
    "cocina": [
        ("preparacion-de-alimentos", 2, "Fui ayudante de cocina en un restaurante de comida rápida."),
        ("cocina-panamena", 2, "Cocino comida típica panameña desde la adolescencia en casa."),
        ("manipulacion-de-alimentos", 2, "Tengo el carné de manipulador de alimentos vigente."),
        ("lavado-de-utensilios", 1, "Me encargaba de lavar utensilios y mantener limpia la cocina."),
    ],
    "servicio": [
        ("servicio-de-mesa", 2, "Atendí mesas en eventos y bodas."),
        ("barista", 1, "Preparaba café espresso en una cafetería del barrio."),
        ("atencion-al-cliente", 2, "Tomaba pedidos y los llevaba a la mesa."),
        ("trabajo-bajo-presion", 2, "En temporada alta atendía muchas mesas a la vez."),
    ],
    "oficina": [
        ("ofimatica-basica", 2, "Manejo Word y correo electrónico para trabajo de oficina."),
        ("excel-basico", 2, "Hacía listas y sumas en Excel para el negocio de mi tía."),
        ("archivo-y-documentacion", 2, "Organicé el archivo de expedientes en mi práctica profesional."),
        ("atencion-telefonica", 1, "Contestaba el teléfono de la oficina."),
        ("redaccion-de-correos", 1, "Redactaba correos a proveedores."),
    ],
    "tecnologia": [
        ("soporte-tecnico-basico", 2, "Ayudo a vecinos a configurar computadoras e impresoras."),
        ("reparacion-de-computadoras", 2, "Arreglo laptops: cambio de disco, memoria y formateo."),
        ("cableado-de-redes", 1, "Hice el cableado de red de un pequeño local."),
        ("programacion-basica", 1, "Aprendí Python básico en un curso en línea."),
    ],
    "digital": [
        ("redes-sociales-negocios", 2, "Manejo el Instagram del negocio de mi familia."),
        ("diseno-grafico-basico", 2, "Diseño artes en Canva para promociones."),
        ("edicion-de-video-basica", 2, "Edito reels con CapCut."),
        ("comercio-electronico", 1, "Monté una tienda en línea pequeña para vender accesorios."),
    ],
    "construccion": [
        ("ayudante-de-obra", 2, "Trabajé de ayudante en una obra residencial."),
        ("herramientas-manuales", 2, "Sé usar herramientas manuales de albañilería."),
        ("albanileria", 1, "Ayudé a bloquear y repellar en la casa de mis abuelos."),
        ("pintura-de-obra", 1, "Pinté apartamentos con mi tío."),
    ],
    "electricidad": [
        ("electricidad-residencial", 2, "Ayudé a un electricista a instalar tomacorrientes y breakers."),
        ("herramientas-electricas", 2, "Uso taladro y esmeril con seguridad."),
        ("lectura-de-planos", 1, "Puedo leer planos eléctricos sencillos."),
    ],
    "cuidado": [
        ("cuidado-adultos-mayores", 2, "Cuidé a mi abuela durante dos años."),
        ("primeros-auxilios", 1, "Tomé un curso de primeros auxilios con la Cruz Roja."),
        ("signos-vitales", 1, "Sé tomar la presión arterial."),
        ("empatia", 2, "Me gusta acompañar y escuchar a las personas mayores."),
    ],
    "seguridad": [
        ("vigilancia-control-accesos", 2, "Hice turnos de vigilancia en la garita de una barriada."),
        ("monitoreo-cctv", 1, "Revisaba las cámaras de seguridad del edificio."),
        ("reporte-de-incidentes", 2, "Llenaba la bitácora de incidentes en cada turno."),
    ],
    "reparto": [
        ("repartidor-en-moto", 2, "Hago delivery en moto para una app."),
        ("licencia-de-conducir", 2, "Tengo licencia de conducir vigente."),
        ("gps-y-mapas", 2, "Me muevo con Waze por toda la ciudad."),
    ],
    "hoteleria": [
        ("housekeeping", 2, "Hice limpieza de habitaciones en un hostal en temporada."),
        ("recepcion-hotelera", 1, "Cubrí la recepción del hostal haciendo check-in."),
        ("ingles-basico", 1, "Tengo inglés básico para saludar y orientar a turistas."),
    ],
}
TRANSVERSAL = [
    ("trabajo-en-equipo", "Me gusta trabajar en equipo; en el colegio coordinaba los proyectos de grupo."),
    ("puntualidad", "Nunca llegué tarde en mi último trabajo."),
    ("responsabilidad", "Me encargaba de abrir el local temprano."),
    ("aprendizaje-rapido", "Aprendo rápido; aprendí el sistema de caja en una semana."),
    ("comunicacion-efectiva", "Explico las cosas con claridad a los clientes."),
    ("iniciativa", "Propuse ordenar la bodega por categorías y lo hicimos."),
]

FEMALE = [
    "María",
    "Yariela",
    "Kathia",
    "Dayana",
    "Yamileth",
    "Lineth",
    "Nathaly",
    "Itzel",
    "Massiel",
    "Arelys",
    "Ericka",
    "Yuriana",
    "Gloriela",
    "Anayansi",
    "Melany",
    "Rosmery",
    "Edilma",
    "Yesenia",
    "Karla",
]
MALE = [
    "José",
    "Luis",
    "Carlos",
    "Kevin",
    "Abdiel",
    "Jhonatan",
    "Ricardo",
    "Eliécer",
    "Joel",
    "Yoel",
    "Edwin",
    "Alexis",
    "Rolando",
    "Francisco",
    "Bryan",
    "Omar",
    "Iván",
    "Moisés",
    "Ulises",
]
SURNAMES = [
    "González",
    "Rodríguez",
    "Pérez",
    "Castillo",
    "Herrera",
    "Sánchez",
    "Batista",
    "Morales",
    "Vega",
    "Ríos",
    "Quintero",
    "Jaén",
    "Samaniego",
    "Pinzón",
    "Barría",
    "Cedeño",
    "De León",
    "Mendoza",
    "Arosemena",
]


def _availability(rng: random.Random, studying: bool) -> list[dict]:
    if studying:
        # Estudia de noche o de tarde: disponible en la mañana/tarde temprana.
        end = rng.choice(["13:00", "15:00", "16:00"])
        days = LV + (["sab"] if rng.random() < 0.6 else [])
        return [{"day": d, "start": "07:00", "end": end} for d in days]
    pattern = rng.choice(["completo", "completo", "fines", "tarde"])
    if pattern == "fines":
        return [{"day": d, "start": "08:00", "end": "20:00"} for d in ["vie", "sab", "dom"]]
    if pattern == "tarde":
        return [{"day": d, "start": "12:00", "end": "22:00"} for d in LV + ["sab"]]
    return [{"day": d, "start": "06:00", "end": "18:00"} for d in LV + ["sab"]]


def build(seed_dir: Path = SEED_DIR) -> list[dict]:
    rng = random.Random(RNG_SEED)
    with open(seed_dir / "locations.csv", encoding="utf-8", newline="") as f:
        locations = [row["key"] for row in csv.DictReader(f)]
    # Sobre-representa Panamá Oeste para que el demo (Ana) tenga pares comparables.
    oeste = [
        k
        for k in locations
        if k
        in {
            "barrio-balboa",
            "barrio-colon",
            "guadalupe",
            "el-coco",
            "puerto-caimito",
            "arraijan",
            "vista-alegre",
            "burunga",
            "veracruz",
            "cerro-silvestre",
        }
    ]
    archetypes = list(ARCHETYPES)

    youth = [ANA]
    for i in range(1, N_YOUTH):
        gender = rng.choices(["femenino", "masculino", "otro", "prefiero_no_decir"], weights=[46, 46, 3, 5])[0]
        pool = FEMALE if gender == "femenino" else MALE if gender == "masculino" else FEMALE + MALE
        name = f"{rng.choice(pool)} {rng.choice(SURNAMES)}"
        arch = archetypes[(i - 1) % len(archetypes)]
        studying = rng.random() < 0.45
        picked = ARCHETYPES[arch][: rng.randint(2, len(ARCHETYPES[arch]))]
        trans = rng.sample(TRANSVERSAL, k=2)
        source = rng.choice(["cv", "cv", "entrevista"])
        skills = [
            {"skill": s, "level": max(1, min(3, lvl + rng.choice([-1, 0, 0, 1]))), "source": source, "evidence": ev}
            for s, lvl, ev in picked
        ] + [{"skill": s, "level": 2, "source": "entrevista", "evidence": ev} for s, ev in trans]
        # Evita duplicados (p. ej. atencion-al-cliente en dos fuentes).
        seen, unique = set(), []
        for sk in skills:
            if sk["skill"] not in seen:
                seen.add(sk["skill"])
                unique.append(sk)
        cv_text = None
        if source == "cv":
            cv_text = f"{name}. " + " ".join(sk["evidence"] for sk in unique if sk["source"] == "cv")
        youth.append(
            {
                "key": f"joven-{i:02d}",
                "display_name": name,
                "birth_year": rng.randint(2000, 2008),
                "gender": gender,
                "location": rng.choice(oeste) if rng.random() < 0.35 else rng.choice(locations),
                "max_commute_min": rng.choice([30, 45, 60, 75, 90]),
                "transport_budget_daily": float(rng.choice([2, 2.5, 3, 3.5, 4, 5, 6])),
                "min_salary": rng.choice([400, 450, 500, 550, 600, 650, 700]),
                "studying": studying,
                "availability": _availability(rng, studying),
                "cv_raw_text": cv_text,
                "is_synthetic": True,
                "persona": arch,
                "skills": unique,
            }
        )
    return youth


def main() -> None:
    youth = build()
    out = SEED_DIR / "youth.json"
    out.write_text(json.dumps(youth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"youth.json: {len(youth)} perfiles")


if __name__ == "__main__":
    main()
