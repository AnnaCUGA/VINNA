# Arquitectura de VINNA-01 (Fase 1)

## Flujo de un mensaje

```
 Usuario ──▶ Interfaz (Tkinter, hilo principal)
                │  cola de peticiones
                ▼
            Worker (un único hilo)
                │
                ▼
            Orchestrator ──¿empieza con "!"?──▶ CommandProcessor ──▶ memoria
                │ no                                  (nunca se guarda en el historial)
                ▼
            build_messages(proveedor)
              = prompt de sistema (Personality + recuerdos relevantes)
              + historial reciente (ShortTermMemory, ventana limitada)
              + mensaje actual
                │
                ▼
            ModelRouter ──▶ OllamaClient (local) / OpenAIClient (nube)
                │
                ▼
            Si hubo respuesta: se guarda la pareja pregunta/respuesta (1 transacción)
                │  cola de resultados
                ▼
            Interfaz: muestra respuesta, ojos en SPEAKING → IDLE
```

## Módulos

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `config.py` | Leer `settings.yaml` + `.env`; valores por defecto | pyyaml |
| `brain/base.py` | `ProviderError`, `ModelResult`, protocolo de proveedor | — |
| `brain/local_model.py` | Cliente HTTP de Ollama (`/api/chat`, `/api/tags`) con urllib | stdlib |
| `brain/cloud_model.py` | Cliente OpenAI; import diferido; traduce errores | openai (opcional) |
| `brain/model_router.py` | Modos LOCAL/CLOUD/HYBRID, respaldo con aviso | base |
| `personality/character.py` | Cargar personalidad y construir el prompt de sistema | pyyaml |
| `memory/database.py` | Conexión SQLite única + `RLock`, transacciones, versión de esquema | sqlite3 |
| `memory/short_term.py` | Historial; ventana por nº de mensajes y caracteres | database |
| `memory/long_term.py` | Recuerdos: crear, listar, corregir, olvidar, caducar, sin duplicados | database |
| `memory/retrieval.py` | Elegir recuerdos relevantes por palabras clave | long_term |
| `memory/privacy.py` | Detectar/ocultar secretos y datos sensibles | — |
| `core/commands.py` | Todos los comandos `!` en un registro único | memoria, router |
| `core/orchestrator.py` | Une todo; seguro desde un hilo; nunca lanza excepciones al usuario | todo lo anterior |
| `core/events.py` | `Reply` y `StatusEvent` que viajan por la cola | — |
| `interface/face.py` | Ojos en Canvas, animación ligera con `after()` | tkinter |
| `interface/expressions.py` | Estados visuales y su apariencia | — |
| `interface/app.py` | Ventana, `Worker`, cola, sondeo cada 50 ms | core, face |

La interfaz no conoce a Ollama ni a OpenAI, y el orquestador no conoce a Tkinter.
Por eso la consola (`--consola`) y, en el futuro, la voz pueden reutilizar el mismo
orquestador.

## Base de datos (`data/vinna.db`)

```sql
messages(id, role['user'|'assistant'], content, provider, created_at)
memories(id, content, normalized, category, kind['permanent'|'temporary'],
         status['active'|'expired'], created_at, updated_at, expires_at)
```

- `normalized` (minúsculas, sin acentos ni puntuación final) evita duplicados.
- `PRAGMA user_version` guarda la versión del esquema para migraciones futuras.
- Las fechas se guardan en UTC (ISO 8601).

## Decisiones y motivos

| Decisión | Motivo |
|---|---|
| Ollama por urllib (sin `requests` ni SDK) | El modo local no necesita dependencias extra |
| OpenAI con import diferido | VINNA arranca sin `openai` instalado |
| Un único hilo de trabajo + colas | Evita congelar Tkinter y evita carreras entre peticiones |
| Una conexión SQLite con candado | Seguro entre hilos; sin bloqueos "database is locked" |
| Guardar pregunta+respuesta juntas y solo si hubo respuesta | Sin mensajes huérfanos ni duplicados en el historial |
| Comandos nunca en el historial | `!borrar-historial` no deja rastro de sí mismo |
| Recuerdos solo por comando explícito | Requisito: guardar únicamente lo autorizado |
| Recuerdos no enviados a la nube por defecto | Privacidad; configurable |
| En HYBRID el respaldo siempre se anuncia | Requisito: nunca cambiar de proveedor en silencio |
| `!borrar-recuerdos` pide la palabra `confirmar` | Evitar borrados accidentales irreversibles |
| Variables `VINNA_OLLAMA_HOST` en vez de `OLLAMA_HOST` | `OLLAMA_HOST` la usa el servidor Ollama (a veces `0.0.0.0`) |
| Sin ChromaDB ni embeddings | Fase 1: SQLite basta; se evaluará en la Fase 2 |

## Puntos de extensión para fases futuras

- **Voz (Fase 3):** un módulo `voice/` que convierta audio en texto y llame a
  `Orchestrator.handle()`; la interfaz ya tiene el estado `LISTENING`.
- **Memoria inteligente (Fase 2):** sustituir `memory/retrieval.select_relevant`
  por búsqueda semántica sin tocar el orquestador.
- **Seguridad/permisos (Fase 7):** `core/permissions.py` se creará cuando existan
  acciones físicas o externas; ningún modelo podrá ejecutarlas directamente.
