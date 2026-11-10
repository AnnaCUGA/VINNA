"""Memoria de largo plazo: recuerdos autorizados explícitamente por el usuario.

Cada recuerdo tiene: id, contenido, categoría, tipo (permanente/temporal),
estado (activo/expirado) y fechas. En la Fase 1 solo se guardan recuerdos
pedidos con un comando (``!recuerda``); VINNA nunca guarda recuerdos por su
cuenta.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from vinna.memory.database import Database, utc_now
from vinna.memory.privacy import looks_sensitive

MAX_MEMORY_CHARS = 500
CATEGORY_RE = re.compile(r"^[a-záéíóúñü0-9_\-]{1,30}$", re.IGNORECASE)


class MemoryValidationError(Exception):
    """Error de validación de un recuerdo (mensaje listo para mostrar al usuario)."""


@dataclass(frozen=True)
class Memory:
    id: int
    content: str
    category: str
    kind: str  # 'permanent' | 'temporary'
    status: str  # 'active' | 'expired'
    created_at: str
    updated_at: str
    expires_at: str | None

    @property
    def date(self) -> str:
        return self.created_at[:10]


def normalize(text: str) -> str:
    """Normaliza para detectar duplicados: minúsculas, sin acentos ni puntuación final."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".!¡?¿;, ")


class LongTermMemory:
    def __init__(self, db: Database, temporary_hours: float = 24):
        self.db = db
        self.temporary_hours = temporary_hours

    # ---------- validación ----------
    @staticmethod
    def _validate(content: str, category: str) -> tuple[str, str]:
        content = (content or "").strip()
        category = (category or "general").strip().lower()
        if not content:
            raise MemoryValidationError("El recuerdo está vacío.")
        if len(content) > MAX_MEMORY_CHARS:
            raise MemoryValidationError(f"El recuerdo es demasiado largo (máximo {MAX_MEMORY_CHARS} caracteres).")
        if not CATEGORY_RE.match(category):
            raise MemoryValidationError("La categoría solo puede tener letras, números, guiones y hasta 30 caracteres.")
        if looks_sensitive(content):
            raise MemoryValidationError(
                "No guardo contraseñas, claves, números de tarjeta ni datos sensibles. "
                "Reformula el recuerdo sin esa información."
            )
        return content, category

    # ---------- operaciones ----------
    def remember(self, content: str, category: str = "general", temporary: bool = False) -> tuple[Memory, bool]:
        """Guarda un recuerdo. Devuelve (recuerdo, creado). Si ya existía, creado=False."""
        content, category = self._validate(content, category)
        self.expire_old()
        norm = normalize(content)
        now = utc_now()
        expires = None
        if temporary:
            expires = (datetime.now(timezone.utc) + timedelta(hours=self.temporary_hours)).isoformat(
                timespec="seconds"
            )
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM memories WHERE normalized = ? AND status = 'active'", (norm,)
            ).fetchone()
            if existing:
                return self._row(existing), False
            cur = conn.execute(
                "INSERT INTO memories (content, normalized, category, kind, status, created_at, updated_at, expires_at)"
                " VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (content, norm, category, "temporary" if temporary else "permanent", now, now, expires),
            )
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row(row), True

    def get(self, memory_id: int) -> Memory | None:
        rows = self.db.query("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return self._row(rows[0]) if rows else None

    def list_active(self, search: str | None = None) -> list[Memory]:
        self.expire_old()
        rows = self.db.query("SELECT * FROM memories WHERE status = 'active' ORDER BY id")
        memories = [self._row(r) for r in rows]
        if search:
            needle = normalize(search)
            memories = [m for m in memories if needle in normalize(m.content) or needle == m.category]
        return memories

    def correct(self, memory_id: int, new_content: str) -> Memory:
        current = self.get(memory_id)
        if current is None or current.status != "active":
            raise MemoryValidationError(f"No existe un recuerdo activo con id {memory_id}.")
        content, _ = self._validate(new_content, current.category)
        norm = normalize(content)
        with self.db.transaction() as conn:
            dup = conn.execute(
                "SELECT id FROM memories WHERE normalized = ? AND status = 'active' AND id != ?",
                (norm, memory_id),
            ).fetchone()
            if dup:
                raise MemoryValidationError(f"Ya existe un recuerdo igual (id {dup['id']}).")
            conn.execute(
                "UPDATE memories SET content = ?, normalized = ?, updated_at = ? WHERE id = ?",
                (content, norm, utc_now(), memory_id),
            )
        return self.get(memory_id)  # type: ignore[return-value]

    def forget(self, memory_id: int) -> bool:
        """Elimina físicamente un recuerdo. Devuelve True si existía."""
        with self.db.transaction() as conn:
            return conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,)).rowcount > 0

    def clear(self) -> int:
        """Elimina todos los recuerdos (activos y expirados). Devuelve cuántos borró."""
        with self.db.transaction() as conn:
            return conn.execute("DELETE FROM memories").rowcount

    def count(self, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM memories" + (" WHERE status = 'active'" if active_only else "")
        return int(self.db.scalar(sql) or 0)

    def expire_old(self) -> int:
        """Marca como expirados los recuerdos temporales cuya fecha ya pasó."""
        with self.db.transaction() as conn:
            return conn.execute(
                "UPDATE memories SET status = 'expired', updated_at = ? "
                "WHERE kind = 'temporary' AND status = 'active' AND expires_at <= ?",
                (utc_now(), utc_now()),
            ).rowcount

    @staticmethod
    def _row(row) -> Memory:
        data = dict(row)
        data.pop("normalized", None)
        return Memory(**data)
