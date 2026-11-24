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
    historial: list | None = None,
    **kwargs,
):
    """
    Llama a ollama.chat con timeout y reintentos ante fallos de
    conexión o respuestas de error del servidor.

    Los errores de petición inválida (HTTP 4xx, p. ej. modelo
    inexistente) no se reintentan. Al agotar los intentos lanza
    OllamaError con un mensaje claro.

    Si se pasa `historial` (lista mutable), apenda por cada intento:
        {"intento": N, "tiempo_s": T, "ok": bool, "error": str|None}
    """

    cliente = ollama.Client(timeout=timeout)
    ultimo_error = None

    for intento in range(reintentos + 1):

        t0 = time.perf_counter()
        try:
            respuesta = cliente.chat(model=model, messages=messages, **kwargs)
            if historial is not None:
                historial.append({
                    "intento": intento + 1,
                    "tiempo_s": round(time.perf_counter() - t0, 2),
                    "ok": True,
                    "error": None,
                })
            return respuesta

        except ollama.ResponseError as error:
            ultimo_error = error
            if historial is not None:
                historial.append({
                    "intento": intento + 1,
                    "tiempo_s": round(time.perf_counter() - t0, 2),
                    "ok": False,
                    "error": str(error)[:120],
                })
            if 400 <= getattr(error, "status_code", 0) < 500:
                break

        except (ConnectionError, TimeoutError, OSError) as error:
            ultimo_error = error
            if historial is not None:
                historial.append({
                    "intento": intento + 1,
                    "tiempo_s": round(time.perf_counter() - t0, 2),
                    "ok": False,
                    "error": str(error)[:120],
                })

        except Exception as error:
            # httpx y similares: se tratan como fallos de transporte.
            ultimo_error = error
            if historial is not None:
                historial.append({
                    "intento": intento + 1,
                    "tiempo_s": round(time.perf_counter() - t0, 2),
                    "ok": False,
                    "error": str(error)[:120],
                })

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
