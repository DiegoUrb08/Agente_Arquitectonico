
from src.models.requirements import (
    Ambiente,
    RequerimientosArquitectonicos
)

from src.models.defaults import calcular_areas_predeterminadas


requerimientos = RequerimientosArquitectonicos(
    tipo_proyecto="vivienda",
    area_total_vivienda_m2=100,

    ambientes=[
        Ambiente(nombre="sala"),
        Ambiente(nombre="comedor"),
        Ambiente(nombre="cocina"),
        Ambiente(nombre="dormitorio", cantidad=2),
        Ambiente(nombre="baño"),
        Ambiente(nombre="lavandería"),
    ]
)


resultado = calcular_areas_predeterminadas(requerimientos)


print("\nDISTRIBUCIÓN AUTOMÁTICA")
print("-" * 40)

total = 0

for ambiente in resultado.ambientes:

    area_grupo = (
        ambiente.area_objetivo_m2 * ambiente.cantidad
    )

    total += area_grupo

    print(
        f"{ambiente.nombre}: "
        f"{ambiente.area_objetivo_m2} m² "
        f"x {ambiente.cantidad}"
    )

print("-" * 40)
print(f"Área de ambientes: {total:.2f} m²")
print(f"Circulación y otros: {100 - total:.2f} m²")
print(f"Área total: 100.00 m²")
