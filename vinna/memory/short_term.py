"""Memoria de trabajo: historial de la conversación.

Se guarda en SQLite para que sobreviva al cierre, pero al modelo solo se le
envía una ventana limitada (número de mensajes y número de caracteres), para
que el contexto no crezca indefinidamente.
"""

from __future__ import annotations

from dataclasses import dataclass

from vinna.memory.database import Database, utc_now
from vinna.memory.privacy import redact_secrets


@dataclass(frozen=True)
class Message:
    id: int
    role: str  # 'user' | 'assistant'
    content: str
    provider: str | None
    created_at: str

    def as_chat(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class ShortTermMemory:
    def __init__(self, db: Database, max_messages: int = 12, max_chars: int = 6000):
        self.db = db
        self.max_messages = max(2, int(max_messages))
        self.max_chars = max(200, int(max_chars))

    def save_exchange(self, user_text: str, assistant_text: str, provider: str | None) -> None:
        """Guarda la pregunta y la respuesta en una sola transacción.

        Si el modelo falló no se llama a este método, así el historial nunca queda
        con un mensaje del usuario sin respuesta ni con duplicados.
        """
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO messages (role, content, provider, created_at) VALUES ('user', ?, NULL, ?)",
                (redact_secrets(user_text), now),
            )
            conn.execute(
                "INSERT INTO messages (role, content, provider, created_at) VALUES ('assistant', ?, ?, ?)",
                (assistant_text, provider, now),
            )

    def recent(self) -> list[Message]:
        """Últimos mensajes en orden cronológico, recortados al presupuesto de caracteres."""
        rows = self.db.query(
            "SELECT id, role, content, provider, created_at FROM messages ORDER BY id DESC LIMIT ?",
            (self.max_messages,),
        )
        selected: list[Message] = []
        total = 0
        for row in rows:  # del más reciente al más antiguo
            total += len(row["content"])
            if selected and total > self.max_chars:
                break
            selected.append(Message(**dict(row)))
        selected.reverse()
        # El historial enviado al modelo debe empezar con un mensaje del usuario.
        while selected and selected[0].role != "user":
            selected.pop(0)
        return selected

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM messages") or 0)

    def clear(self) -> int:
        """Borra todo el historial y devuelve cuántos mensajes se eliminaron."""
        with self.db.transaction() as conn:
            return conn.execute("DELETE FROM messages").rowcount
