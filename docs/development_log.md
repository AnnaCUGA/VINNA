# Registro de desarrollo de VINNA-01

## 2026-11-10 — Fase 0 (auditoría) y Fase 1 (cerebro funcional) · v0.1.0

### Fase 0 — Estado inicial encontrado

- No existía repositorio ni código del prototipo (`main.py`, `brain.py`, `memory.py`,
  `personality.py`). Se confirmó con la responsable del proyecto: crear una
  implementación limpia.
- Nombre del paquete: se usa `vinna` (el documento mencionaba `python -m nixo.main`;
  se confirmó que el nombre es VINNA).
- Entorno de desarrollo usado: Linux, Python 3.12.3 con Tkinter 8.6, sin Ollama ni
  OpenAI. Entorno objetivo: Windows + Python 3.12.
- Los 15 problemas listados en la sección 10 del documento maestro se trataron como
  requisitos de diseño (no había código que auditar).

### Qué se implementó

| Área | Archivos |
|---|---|
| Configuración | `vinna/config.py`, `config/settings.yaml`, `config/personality.yaml`, `.env.example` |
| Cerebro | `vinna/brain/base.py`, `local_model.py`, `cloud_model.py`, `model_router.py` |
| Personalidad | `vinna/personality/character.py` |
| Memoria | `vinna/memory/database.py`, `short_term.py`, `long_term.py`, `retrieval.py`, `privacy.py` |
| Núcleo | `vinna/core/orchestrator.py`, `commands.py`, `events.py` |
| Interfaz | `vinna/interface/app.py`, `face.py`, `expressions.py` |
| Arranque | `vinna/main.py` (ventana, `--consola`, `--diagnostico`, `--modo`) |
| Pruebas | `tests/conftest.py`, `test_brain.py`, `test_memory.py`, `test_personality.py`, `test_orchestrator.py`, `test_interface.py` |
| Documentación | `README.md`, `docs/architecture.md`, este archivo |

### Cómo se resolvió cada problema de la sección 10

| Problema | Solución |
|---|---|
| Importaciones al ejecutar con `-m` | Todo usa imports absolutos `vinna.…`; se ejecuta con `python -m vinna.main` |
| Imports innecesarios | Verificado con pyflakes: 0 avisos |
| Contexto correcto al modelo | `build_messages`: sistema + historial + mensaje actual (probado, sin duplicar el mensaje) |
| Comandos guardados como conversación | Los comandos se resuelven antes del modelo y nunca se guardan |
| Borrado de historial deja el comando | Igual que arriba; la prueba verifica 0 mensajes tras borrar |
| Respuestas guardadas correctamente | Pregunta y respuesta se guardan juntas en una transacción, solo si hubo respuesta |
| Ollama no disponible | `ProviderError` con mensajes claros (no conecta / falta modelo / tiempo agotado) |
| OpenAI no configurado | Mensaje claro; la biblioteca se importa solo si se usa |
| Interfaz congelada | Hilo de trabajo + colas + `after()`; probado con un modelo lento |
| Carreras entre hilos y SQLite | Una conexión con `RLock`; prueba con 4 hilos escribiendo a la vez |
| Estados visuales fuera del hilo principal | Solo `_poll()` (hilo principal) toca widgets |
| Mensajes duplicados | Botón desactivado mientras piensa + guardado único por intercambio |
| Contexto que crece sin límite | Ventana por nº de mensajes (12) y caracteres (6000) |
| Persistencia de recuerdos | Transacciones confirmadas; prueba que cierra y reabre la base de datos |

### Errores encontrados durante el desarrollo

- `OLLAMA_HOST` choca con la variable que usa el propio servidor Ollama (puede valer
  `0.0.0.0`, inválido como destino en Windows) → se renombró a `VINNA_OLLAMA_HOST`.
- El atributo `state` del rostro podía confundirse con métodos de Tk → `visual_state`.
- En Windows, imprimir ✔/✘ con la salida redirigida podía fallar por codificación →
  `stream.reconfigure(errors="replace")`.

### Pruebas ejecutadas

`xvfb-run python3.12 -m pytest` → **53 pasadas, 0 fallidas** (sin pantalla: 50 pasadas, 3 omitidas).

| Criterio (sección 13) | Cobertura |
|---|---|
| 1 Inicio | `test_window_opens_and_shows_states` + arranque real de `--diagnostico`/`--consola` |
| 2 Conversación | Servidor HTTP que imita la API de Ollama + orquestador con modelo simulado |
| 3 Personalidad | `test_personality.py` |
| 4 Memoria | `test_remember_and_list`, comandos `!recuerda`/`!recuerdos` |
| 5 Persistencia | `test_persistence_after_reopen` |
| 6 Eliminación | `test_forget_specific_memory`, `!olvida` |
| 7 Historial | `test_clear_history_does_not_keep_the_command` |
| 8 Modo local | Cliente Ollama probado contra servidor local, sin Internet |
| 9 Modo nube | SDK de OpenAI simulado + error claro sin clave |
| 10 Respaldo híbrido | `test_hybrid_falls_back_to_local_with_notice` |
| 11 Interfaz responde | `test_ui_stays_responsive_while_model_thinks` (modelo de 1 s) |
| 12 Errores | Errores de proveedor y excepciones inesperadas no cierran el programa |

### Pendiente de verificación manual (en Windows)

Las pruebas 2, 8 y 9 se validaron con servidores/SDK simulados; falta comprobarlas
con Ollama real y una clave real de OpenAI (ver lista en el README).

### Pendiente para la Fase 2

- Recuperación semántica (embeddings) si la búsqueda por palabras clave se queda corta.
- Clasificación automática de categorías; sugerir (no guardar) recuerdos.
- Búsqueda avanzada y detección de recuerdos casi duplicados.
- Revisar si `qwen2.5:0.5b` sigue bien la personalidad en español; quizá `qwen2.5:1.5b`.
