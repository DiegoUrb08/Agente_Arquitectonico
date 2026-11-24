import unicodedata


def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza el nombre de un ambiente: minúsculas, sin espacios
    sobrantes y sin tildes ("Baño" -> "bano").
    """

    texto = str(nombre).strip().lower()
    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
