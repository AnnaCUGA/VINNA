"""Orquestador: el "cerebro central" que une personalidad, memoria, comandos y modelos.

No depende de la interfaz: puede usarse desde Tkinter, desde la consola o, en
fases futuras, desde la voz. Es seguro llamarlo desde un hilo de trabajo.
"""

from __future__ import annotations

import logging
import threading

from vinna.brain.model_router import ModelRouter, RouterError
from vinna.config import Settings
from vinna.core.commands import CommandProcessor, is_command
from vinna.core.events import Reply, ReplyKind, StatusEvent
from vinna.memory.database import Database
from vinna.memory.long_term import LongTermMemory
from vinna.memory.pronouns import to_second_person
from vinna.memory.recall import format_recall, is_recall_question
from vinna.memory.retrieval import select_relevant
from vinna.memory.short_term import ShortTermMemory
from vinna.personality.character import Personality

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000
MEMORY_PROVIDER = "memoria"  # respuestas generadas desde la base de datos, sin modelo


class Orchestrator:
    def __init__(self, settings: Settings, personality: Personality, db: Database, router: ModelRouter):
        self.settings = settings
        self.personality = personality
        self.db = db
        self.router = router
        mem = settings.memory
        self.short_term = ShortTermMemory(db, mem["context_messages"], mem["context_max_chars"])
        self.long_term = LongTermMemory(db, mem["temporary_hours"])
        self.commands = CommandProcessor(self.long_term, self.short_term, router)
        self._lock = threading.Lock()  # una petición a la vez

    # ---------- construcción del contexto ----------
    def build_messages(self, user_text: str, provider: str) -> list[dict[str, str]]:
        """Mensajes para el modelo: sistema (personalidad + recuerdos) + historial + mensaje actual."""
        include_memories = provider == "local" or bool(self.settings.privacy.get("send_memories_to_cloud"))
        memories = []
        if include_memories:
            memories = select_relevant(
                self.long_term.list_active(), user_text, self.settings.memory["max_memories_in_prompt"]
            )
        messages = [{"role": "system", "content": self.personality.build_system_prompt(memories)}]
        messages.extend(m.as_chat() for m in self.short_term.recent())
        if memories:
            # Los modelos pequeños atienden más a lo último que leen: se repiten los
            # datos del usuario justo antes de su mensaje.
            facts = "; ".join(f"«{to_second_person(m.content)}»" for m in memories)
            messages.append({
                "role": "system",
                "content": f"Recordatorio: el usuario te pidió recordar esto: {facts}. "
                           "Úsalo si su mensaje tiene que ver con ello y háblale en segunda persona "
                           "(«te gusta…», «tu…»): son datos del usuario, no tuyos.",
            })
        messages.append({"role": "user", "content": user_text})
        return messages

    # ---------- entrada principal ----------
    def handle(self, text: str) -> Reply | None:
        text = (text or "").strip()
        if not text:
            return None
        with self._lock:
            if is_command(text):
                result = self.commands.execute(text)
                return Reply(
                    result.text,
                    ReplyKind.COMMAND if result.ok else ReplyKind.ERROR,
                    refresh_status=result.refresh_status,
                )
            if len(text) > MAX_INPUT_CHARS:
                return Reply(f"El mensaje es demasiado largo (máximo {MAX_INPUT_CHARS} caracteres).", ReplyKind.ERROR)
            if is_recall_question(text):
                # "¿Qué recuerdas de mí?" se responde desde la base de datos, sin el modelo.
                answer = format_recall(self.long_term.list_active())
                self.short_term.save_exchange(text, answer, MEMORY_PROVIDER)
                return Reply(answer, ReplyKind.ASSISTANT, provider=MEMORY_PROVIDER)
            try:
                result = self.router.generate(text, lambda provider: self.build_messages(text, provider))
            except RouterError as exc:
                return Reply(str(exc), ReplyKind.ERROR)
            except Exception:  # noqa: BLE001 - nunca cerrar el programa por un fallo inesperado
                log.exception("Error inesperado al generar respuesta")
                return Reply("Ocurrió un error inesperado. Revisa data/vinna.log para más detalles.", ReplyKind.ERROR)
            # Se guarda la pareja pregunta/respuesta solo cuando hubo respuesta.
            self.short_term.save_exchange(text, result.text, result.provider)
            return Reply(result.text, ReplyKind.ASSISTANT, provider=result.provider, notice=result.fallback_notice)

    def connection_status(self) -> StatusEvent:
        status = self.router.status()
        local_ok, local_detail = status["local"]
        cloud_ok, cloud_detail = status["cloud"]
        return StatusEvent(self.router.mode.value, local_ok, local_detail, cloud_ok, cloud_detail)
