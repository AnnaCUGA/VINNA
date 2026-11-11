# VINNA-01

VINNA es un **robot de escritorio inteligente**, modular y evolutivo. Esta versión
(0.1.0, Fase 1) es el **cerebro** funcionando en la computadora: conversa, tiene
personalidad, recuerda lo que le autorizas y muestra un rostro con ojos animados.
La voz, la visión y el cuerpo físico llegarán en fases posteriores.

VINNA es un programa de IA: no tiene conciencia ni sentimientos humanos.

## Requisitos

- Windows 10/11
- **Python 3.12** (al instalarlo marca *Add python.exe to PATH* y *tcl/tk and IDLE*)
- **Ollama** para el modo local: <https://ollama.com/download>
- Opcional: una clave de OpenAI para los modos nube/híbrido

## Instalación (PowerShell, dentro de la carpeta VINNA-01)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # si da error de permisos: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -r requirements.txt

# Modelo local
ollama pull qwen2.5:1.5b          # ~1 GB; qwen2.5:0.5b (~400 MB) es más ligero pero menos preciso

# Opcional (nube):
python -m pip install -r requirements-cloud.txt
copy .env.example .env                # y escribe tu OPENAI_API_KEY dentro de .env
```

## Ejecución

```powershell
python -m vinna.main                  # ventana con el rostro de VINNA
python -m vinna.main --diagnostico    # comprueba Python, Tkinter, Ollama y OpenAI
python -m vinna.main --consola        # modo texto, sin ventana
python -m vinna.main --modo hibrido   # cambia el modo solo para esta ejecución
python -m pytest                      # pruebas automáticas
```

Siempre ejecuta los comandos **desde la carpeta VINNA-01** (la que contiene `vinna/`).

## Configuración

| Archivo | Para qué sirve |
|---|---|
| `config/settings.yaml` | Modo de IA, modelos, límites de memoria, interfaz, registros |
| `config/personality.yaml` | Nombre, idioma, tono, formalidad, longitud, rasgos y reglas de VINNA |
| `.env` | Clave de OpenAI y valores que sobrescriben `settings.yaml` (no se sube a git) |

### Modos de IA

| Modo | Comportamiento |
|---|---|
| `LOCAL` | Solo Ollama. Funciona sin Internet ni clave. Si falla, muestra el error. |
| `CLOUD` | Solo OpenAI. Si falla, muestra el error (no cambia a local en silencio). |
| `HYBRID` | Elige proveedor (preferido o según complejidad) y usa el otro como respaldo **avisando** en el chat. |

Por privacidad, los recuerdos **no se envían a la nube** salvo que actives
`privacy.send_memories_to_cloud: true`.

## Comandos

| Comando | Acción |
|---|---|
| `!recuerda [#categoria] <texto>` | Guarda un recuerdo permanente |
| `!recuerda-temporal [#categoria] <texto>` | Guarda un recuerdo que caduca (24 h por defecto) |
| `!recuerdos [texto]` | Lista los recuerdos activos (con filtro opcional) |
| `!corrige <id> <texto>` | Corrige un recuerdo |
| `!olvida <id>` | Elimina un recuerdo y verifica que desapareció |
| `!borrar-recuerdos confirmar` | Elimina todos los recuerdos (pide confirmación) |
| `!borrar-historial` | Borra la conversación (el comando no queda guardado) |
| `!modo [local\|nube\|hibrido]` | Muestra o cambia el modo de IA |
| `!estado` | Comprueba Ollama, OpenAI y la memoria |
| `!ayuda` | Lista de comandos |

VINNA rechaza guardar contraseñas, claves API, números de tarjeta y datos similares.

## Arquitectura (resumen)

```
vinna/
  main.py            arranque (ventana, consola o diagnóstico)
  config.py          carga settings.yaml y .env
  brain/             Ollama, OpenAI y enrutador de modelos
  memory/            SQLite: historial (trabajo) y recuerdos (largo plazo)
  personality/       personalidad independiente del modelo
  core/              orquestador, comandos y eventos
  interface/         ventana Tkinter y rostro animado
```

Detalle completo en [`docs/architecture.md`](docs/architecture.md). Historial de
cambios y pruebas en [`docs/development_log.md`](docs/development_log.md).

## Estado de desarrollo

- ✅ Fase 0 — Auditoría
- ✅ Fase 1 — Cerebro funcional (pendiente de verificación manual en Windows)
- ⏳ Fase 2 — Memoria inteligente
- ⏳ Fases 3–8 — Voz, interfaz avanzada, visión, cuerpo físico, autonomía, aprendizaje
