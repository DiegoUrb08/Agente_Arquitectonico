"""
Benchmark manual del interprete (Ollama + Qwen) con peticiones reales.

Uso (desde la raiz del proyecto, con Ollama en marcha):

    python scripts/benchmark_llm.py [salida.json] [--solo N]

Para cada peticion mide: validez del JSON/esquema, tiempo, fidelidad frente
a lo esperado (terreno, ambientes, cantidades, areas, relaciones) y si el
plano completo se genera despues. Guarda los resultados de forma incremental.
"""

import json
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.ai.interpreter import interpretar_instruccion  # noqa: E402
from src.services.pipeline import generar_plano  # noqa: E402

# esperado: terreno (ancho, largo) | area_terreno; ambientes {base: cantidad};
# areas {base: m2 pedidos}; relaciones [(a, b)]; fuera_catalogo: se espera
# que NO aparezca ese ambiente.
CASOS = [
    {"id": "basico",
     "prompt": "Quiero una casa en un terreno de 10 x 20 metros con 2 dormitorios, 1 baño, sala, comedor y cocina.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 2, "bano": 1, "sala": 1, "comedor": 1, "cocina": 1}},
    {"id": "areas_explicitas",
     "prompt": "Vivienda en terreno de 12 x 18 m. La sala debe tener 25 m2, la cocina 12 m2 y los 3 dormitorios 12 m2 cada uno. Un baño y un comedor.",
     "terreno": (12, 18),
     "ambientes": {"sala": 1, "cocina": 1, "dormitorio": 3, "bano": 1, "comedor": 1},
     "areas": {"sala": 25, "cocina": 12, "dormitorio": 12}},
    {"id": "relaciones",
     "prompt": "Casa de 9 x 16 metros: sala, cocina, 2 dormitorios y 2 baños. La cocina debe estar junto a la sala y cada dormitorio junto a un baño.",
     "terreno": (9, 16),
     "ambientes": {"sala": 1, "cocina": 1, "dormitorio": 2, "bano": 2},
     "relaciones": [("cocina", "sala"), ("dormitorio", "bano")]},
    {"id": "solo_area_terreno",
     "prompt": "Tengo un terreno de 200 m2 y quiero una casa con 3 dormitorios, 2 baños, sala y cocina.",
     "area_terreno": 200,
     "ambientes": {"dormitorio": 3, "bano": 2, "sala": 1, "cocina": 1}},
    {"id": "ambientes_extra",
     "prompt": "Casa en terreno de 10 x 22 m con sala, comedor, cocina, 3 dormitorios, 2 baños, un estudio y un cuarto de lavanderia.",
     "terreno": (10, 22),
     "ambientes": {"sala": 1, "comedor": 1, "cocina": 1, "dormitorio": 3, "bano": 2, "estudio": 1, "lavanderia": 1}},
    {"id": "minimo",
     "prompt": "Departamento pequeño de 6 x 10 metros con un dormitorio, un baño y una cocina integrada a la sala.",
     "terreno": (6, 10),
     "ambientes": {"dormitorio": 1, "bano": 1, "cocina": 1, "sala": 1}},
    {"id": "habitantes",
     "prompt": "Casa para una familia de 5 personas en un terreno de 11 x 20 m. Necesitamos 3 dormitorios, 2 baños, sala-comedor y cocina.",
     "terreno": (11, 20),
     "ambientes": {"dormitorio": 3, "bano": 2, "cocina": 1}},
    {"id": "dos_pisos",
     "prompt": "Casa de 2 pisos en un terreno de 8 x 15 m con sala, cocina, comedor, 3 dormitorios y 2 baños.",
     "terreno": (8, 15),
     "ambientes": {"sala": 1, "cocina": 1, "comedor": 1, "dormitorio": 3, "bano": 2}},
    {"id": "area_total",
     "prompt": "Quiero construir 120 m2 en un terreno de 10 x 20 m, con 3 dormitorios, 2 baños, sala, comedor y cocina.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 3, "bano": 2, "sala": 1, "comedor": 1, "cocina": 1}},
    {"id": "numeros_en_letras",
     "prompt": "Necesito una vivienda en un lote de diez por veinte metros, con dos dormitorios, dos baños, una sala y una cocina.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 2, "bano": 2, "sala": 1, "cocina": 1}},
    {"id": "informal",
     "prompt": "una casita de 7x14, con 2 cuartos, baño, cocina y sala nomas",
     "terreno": (7, 14),
     "ambientes": {"dormitorio": 2, "bano": 1, "cocina": 1, "sala": 1}},
    {"id": "grande",
     "prompt": "Residencia en terreno de 15 x 30 m: sala, comedor, cocina, 4 dormitorios, 3 baños, estudio, sala de estar y lavanderia. La cocina junto al comedor.",
     "terreno": (15, 30),
     "ambientes": {"sala": 1, "comedor": 1, "cocina": 1, "dormitorio": 4, "bano": 3, "estudio": 1},
     "relaciones": [("cocina", "comedor")]},
    {"id": "fuera_catalogo",
     "prompt": "Casa de 10 x 20 m con sala, cocina, 2 dormitorios, 1 baño y una piscina.",
     "terreno": (10, 20),
     "ambientes": {"sala": 1, "cocina": 1, "dormitorio": 2, "bano": 1},
     "fuera_catalogo": "piscina"},
    {"id": "garaje",
     "prompt": "Vivienda en 9 x 18 m con garaje, sala, cocina, 2 dormitorios y baño.",
     "terreno": (9, 18),
     "ambientes": {"sala": 1, "cocina": 1, "dormitorio": 2, "bano": 1, "garaje": 1}},
    {"id": "ambiguo",
     "prompt": "Quiero una casa bonita y comoda.",
     "ambiguo": True},
    {"id": "sin_terreno",
     "prompt": "Casa con 2 dormitorios, 1 baño, sala y cocina.",
     "ambientes": {"dormitorio": 2, "bano": 1, "sala": 1, "cocina": 1},
     "sin_terreno": True},
    {"id": "dormitorio_con_bano",
     "prompt": "Terreno de 10 x 20 m. 3 dormitorios, el principal con su baño propio, otro baño compartido, sala, cocina y comedor.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 3, "bano": 2, "sala": 1, "cocina": 1, "comedor": 1}},
    {"id": "areas_minimas",
     "prompt": "Terreno de 10 x 20 m. Dormitorios de al menos 14 m2 (serán 2), sala de mínimo 20 m2, cocina, comedor y un baño.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 2, "sala": 1, "cocina": 1, "comedor": 1, "bano": 1},
     "areas": {"dormitorio": 14, "sala": 20}},
    {"id": "ingles_mezclado",
     "prompt": "House on a 10 x 20 meter lot with 2 bedrooms, 1 bathroom, living room and kitchen.",
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 2, "bano": 1, "sala": 1, "cocina": 1}},
    {"id": "texto_largo",
     "prompt": ("Somos una pareja joven y vamos a construir nuestra primera casa. "
                "El lote mide 10 metros de frente por 20 de fondo. Queremos 2 dormitorios, "
                "uno de ellos con baño, un baño de visitas, una sala amplia, un comedor, "
                "una cocina que se conecte con el comedor y un pequeño estudio para trabajar."),
     "terreno": (10, 20),
     "ambientes": {"dormitorio": 2, "bano": 2, "sala": 1, "comedor": 1, "cocina": 1, "estudio": 1},
     "relaciones": [("cocina", "comedor")]},
]


def _norm(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", "", texto).strip()


def _base(nombre):
    """'Dormitorios' / 'dormitorio principal' / 'baños' -> base canonica."""
    n = _norm(nombre)
    for clave in ("dormitorio", "cuarto", "habitacion", "bano", "sala", "comedor",
                  "cocina", "estudio", "lavanderia", "garaje", "cochera"):
        if clave in n:
            return {"cuarto": "dormitorio", "habitacion": "dormitorio",
                    "cochera": "garaje"}.get(clave, clave)
    return n


def _agrupar(req):
    grupos = {}
    for a in req.ambientes:
        grupos.setdefault(_base(a.nombre), []).append(a)
    return grupos


def evaluar(caso, req):
    """Compara la interpretacion con lo esperado. Devuelve dict de metricas."""
    r = {}
    esperado = caso.get("ambientes", {})
    grupos = _agrupar(req)
    obtenido = {b: sum(a.cantidad for a in l) for b, l in grupos.items()}

    r["ambientes_esperados"] = esperado
    r["ambientes_obtenidos"] = obtenido
    r["faltan"] = sorted(b for b in esperado if b not in obtenido)
    r["cantidad_incorrecta"] = sorted(
        b for b, c in esperado.items() if b in obtenido and obtenido[b] != c)
    r["sobran"] = sorted(b for b in obtenido if b not in esperado)
    r["ambientes_ok"] = not r["faltan"] and not r["cantidad_incorrecta"]

    if "terreno" in caso:
        ancho, largo = caso["terreno"]
        # El modelo puede invertir ancho/largo; se acepta cualquier orden.
        got = {req.ancho_terreno_m, req.largo_terreno_m}
        r["terreno_ok"] = got == {float(ancho), float(largo)}
        r["terreno_obtenido"] = [req.ancho_terreno_m, req.largo_terreno_m]
    elif "area_terreno" in caso:
        area = (req.ancho_terreno_m or 0) * (req.largo_terreno_m or 0)
        r["terreno_ok"] = abs(area - caso["area_terreno"]) <= caso["area_terreno"] * 0.05 \
            or req.area_terreno_m2 == caso["area_terreno"]
        r["terreno_obtenido"] = [req.ancho_terreno_m, req.largo_terreno_m, req.area_terreno_m2]

    if "areas" in caso:
        malas = []
        for base, pedido in caso["areas"].items():
            ambs = grupos.get(base, [])
            ok = any(
                any(v is not None and abs(v - pedido) <= 0.5
                    for v in (a.area_minima_m2, a.area_objetivo_m2))
                for a in ambs
            ) if ambs else False
            if not ok:
                malas.append(base)
        r["areas_incorrectas"] = malas
        r["areas_ok"] = not malas

    if "relaciones" in caso:
        presentes = set()
        for rel in req.relaciones_adyacencia:
            if isinstance(rel, dict):
                par = (rel.get("ambiente_a"), rel.get("ambiente_b"))
            else:
                par = tuple(rel[:2])
            presentes.add(frozenset((_base(par[0]), _base(par[1]))))
        faltan = [list(p) for p in caso["relaciones"]
                  if frozenset(p) not in presentes]
        r["relaciones_faltan"] = faltan
        r["relaciones_ok"] = not faltan
    r["relaciones_inventadas"] = (
        len(req.relaciones_adyacencia) if "relaciones" not in caso else None)

    if "fuera_catalogo" in caso:
        r["fuera_catalogo_presente"] = _base(caso["fuera_catalogo"]) in obtenido or any(
            caso["fuera_catalogo"] in _norm(a.nombre) for a in req.ambientes)
    return r


def correr(caso):
    res = {"id": caso["id"], "prompt": caso["prompt"]}
    t0 = time.perf_counter()
    try:
        req = interpretar_instruccion(caso["prompt"])
    except Exception as error:  # el benchmark debe continuar siempre
        res.update(interpretacion="error", error=f"{type(error).__name__}: {str(error)[:300]}",
                   tiempo_interpretacion_s=round(time.perf_counter() - t0, 1))
        return res
    res["tiempo_interpretacion_s"] = round(time.perf_counter() - t0, 1)
    res["interpretacion"] = "ok"
    res["requerimientos"] = req.model_dump()
    if not caso.get("ambiguo"):
        res["evaluacion"] = evaluar(caso, req)

    t1 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as d:
            plano = generar_plano(req, Path(d) / "p.dxf")
        res["plano"] = "ok"
        res["ambientes_en_plano"] = len(plano.distribucion)
        res["conectado"] = plano.validacion["distribucion_conectada"]
        res["ventanas"] = plano.aberturas["cantidad_ventanas"]
        res["puertas"] = plano.aberturas["cantidad_puertas"]
    except Exception as error:
        res["plano"] = "error"
        res["error_plano"] = f"{type(error).__name__}: {str(error)[:300]}"
    res["tiempo_plano_s"] = round(time.perf_counter() - t1, 1)
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    salida = Path(args[0]) if args else RAIZ / "docs" / "benchmark_llm.json"
    casos = CASOS
    if "--solo" in sys.argv:
        casos = CASOS[:int(sys.argv[sys.argv.index("--solo") + 1])]

    resultados = []
    for i, caso in enumerate(casos, 1):
        print(f"[{i}/{len(casos)}] {caso['id']} ...", flush=True)
        res = correr(caso)
        resultados.append(res)
        obs_llm = [o for o in (res.get("requerimientos") or {}).get("observaciones", [])
                   if o.startswith("[LLM]")]
        extra = f" {obs_llm[0]}" if obs_llm else ""
        print(f"    interpretacion={res['interpretacion']} "
              f"{res['tiempo_interpretacion_s']}s plano={res.get('plano')}{extra}", flush=True)
        salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LISTO", salida)


if __name__ == "__main__":
    main()
