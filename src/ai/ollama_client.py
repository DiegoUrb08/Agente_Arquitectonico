import time

import ollama


# Nombre del modelo instalado en Ollama
MODEL_NAME = "qwen3:8b"

# Parámetros de robustez de la comunicación con Ollama.
TIMEOUT_SEGUNDOS = 180
REINTENTOS = 2
ESPERA_REINTENTO_SEGUNDOS = 2


class OllamaError(RuntimeError):
    """Error de comunicación con el servidor Ollama."""


def chat_con_reintentos(
    *,
    messages,
    model: str = MODEL_NAME,
    reintentos: int = REINTENTOS,
    timeout: float = TIMEOUT_SEGUNDOS,
    espera: float = ESPERA_REINTENTO_SEGUNDOS,
    **kwargs,
):
    """
    Llama a ollama.chat con timeout y reintentos ante fallos de
    conexión o respuestas de error del servidor.

    Los errores de petición inválida (HTTP 4xx, p. ej. modelo
    inexistente) no se reintentan. Al agotar los intentos lanza
    OllamaError con un mensaje claro.
    """

    cliente = ollama.Client(timeout=timeout)
    ultimo_error = None

    for intento in range(reintentos + 1):

        try:
            return cliente.chat(model=model, messages=messages, **kwargs)

        except ollama.ResponseError as error:
            ultimo_error = error
            if 400 <= getattr(error, "status_code", 0) < 500:
                break

        except (ConnectionError, TimeoutError, OSError) as error:
            ultimo_error = error

        except Exception as error:
            # httpx y similares: se tratan como fallos de transporte.
            ultimo_error = error

        if intento < reintentos:
            time.sleep(espera)

    raise OllamaError(
        f"No se pudo obtener respuesta de Ollama (modelo '{model}'): "
        f"{ultimo_error}"
    ) from ultimo_error


def consultar_modelo(mensaje: str) -> str:
    """
    Envía un mensaje al modelo local de Ollama
    y devuelve su respuesta.
    """

    try:
        respuesta = chat_con_reintentos(
            messages=[{"role": "user", "content": mensaje}]
        )
        return respuesta["message"]["content"]

    except OllamaError as error:
        return f"Error al comunicarse con Ollama: {error}"


if __name__ == "__main__":

    pregunta = (
        "Explica qué es un plano arquitectónico "
        "y cuáles son sus elementos principales."
    )

    print("\nRESPUESTA DEL MODELO:\n")
    print(consultar_modelo(pregunta))
