"""Constantes y utilidades comunes de la exportación DXF."""

APP_ID = "AGENTE_ARQ"

# Contrato entre el generador y el editor de DXF: nombres de capa y
# unidades (6 = metros) que el editor espera encontrar.
CAPA_TERRENO = "TERRENO"
CAPA_AMBIENTES = "AMBIENTES"
CAPA_TEXTOS = "TEXTOS"
UNIDADES_METROS = 6


# ==========================================
# METADATOS
# ==========================================

def registrar_metadatos(
    entidad,
    identificador,
    nombre
):
    """Guarda información mediante XDATA."""

    entidad.set_xdata(
        APP_ID,
        [
            (1000, str(identificador)),
            (1000, str(nombre)),
        ]
    )
