"""Botón de pantalla completa para los visores del plano (iframes 2D y 3D)."""

TEXTO_ENTRAR = "Pantalla completa"
TEXTO_SALIR = "Salir de pantalla completa (Esc)"

# Botón + script. El iframe de Streamlit permite `fullscreen` en su política;
# si el navegador no lo admite, el botón no aparece.
BOTON = f"""<button id="pantalla-completa" class="pantalla-completa" type="button"
  aria-pressed="false" hidden>{TEXTO_ENTRAR}</button>
<script>
(function () {{
  var boton = document.getElementById("pantalla-completa");
  var raiz = document.documentElement;
  if (!boton || !document.fullscreenEnabled || !raiz.requestFullscreen) return;
  boton.hidden = false;
  function actualizar() {{
    var activa = Boolean(document.fullscreenElement);
    boton.textContent = activa ? "{TEXTO_SALIR}" : "{TEXTO_ENTRAR}";
    boton.setAttribute("aria-pressed", String(activa));
  }}
  boton.addEventListener("click", function () {{
    if (document.fullscreenElement) document.exitFullscreen();
    else raiz.requestFullscreen().catch(function () {{}});
  }});
  document.addEventListener("fullscreenchange", actualizar);
}})();
</script>"""

# Estilo para el visor 2D, donde el botón va solo en la esquina.
ESTILO_2D = """
.pantalla-completa { position: absolute; top: 8px; right: 8px;
  background: #10263FE6; color: #E6F1FF; border: 1px solid #2A4D72;
  border-radius: 8px; padding: 6px 10px; font: 12px "Segoe UI", Inter,
  system-ui, sans-serif; cursor: pointer; }
.pantalla-completa:hover { border-color: #38BDF8; color: #38BDF8; }
[hidden] { display: none !important; }
html:fullscreen, html:fullscreen body { background: #0A1A2F; }
"""


def documento_svg(svg: str) -> str:
    """Página del visor 2D: el SVG a todo el alto y el botón de pantalla completa."""
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<style>html,body{height:100%;margin:0;overflow:hidden;"
        f"background:transparent;position:relative}}{ESTILO_2D}</style></head>"
        f"<body>{svg}{BOTON}</body></html>"
    )
