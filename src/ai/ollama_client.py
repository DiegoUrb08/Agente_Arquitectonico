import ollama


# Nombre del modelo instalado en Ollama
MODEL_NAME = "qwen3:8b"


def consultar_modelo(mensaje: str) -> str:
    """
    Envía un mensaje al modelo local de Ollama
    y devuelve su respuesta.
    """

    try:
        respuesta = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": mensaje
                }
            ]
        )

        return respuesta["message"]["content"]

    except Exception as error:
        return f"Error al comunicarse con Ollama: {error}"


if __name__ == "__main__":

    pregunta = (
        "Explica qué es un plano arquitectónico "
        "y cuáles son sus elementos principales."
    )

    resultado = consultar_modelo(pregunta)

    print("\nRESPUESTA DEL MODELO:\n")
    print(resultado)
