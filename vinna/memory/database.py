"""Acceso a SQLite para VINNA.

Decisiones importantes:
- Una sola conexión compartida protegida por un ``threading.RLock``. La interfaz
  y el hilo de trabajo pueden usar la base de datos sin condiciones de carrera.
- Cada escritura se hace dentro de una transacción (``with self._conn``), por lo
  que se confirma en disco al terminar o se revierte si hay error. Así los
  recuerdos sobreviven al cierre del programa.
- El esquema tiene versión (``PRAGMA user_version``) para poder migrarlo en
  fases futuras sin perder datos.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    provider    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    kind        TEXT NOT NULL DEFAULT 'permanent' CHECK (kind IN ('permanent', 'temporary')),
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    expires_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_normalized ON memories(normalized);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Envoltorio seguro para hilos sobre una conexión SQLite."""

    def __init__(self, path: Path | str):
        self.path = Path(path) if str(path) != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # check_same_thread=False es seguro porque todo acceso pasa por el candado.
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._closed = False
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._migrate()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            with self._conn:
                self._conn.executescript(SCHEMA)
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Bloquea la conexión y abre una transacción (commit/rollback automático)."""
        with self._lock:
            self._ensure_open()
            with self._conn:
                yield self._conn

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            self._ensure_open()
            return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.execute(sql, params)

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        rows = self.query(sql, params)
        return rows[0][0] if rows else None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("La base de datos ya está cerrada.")

    def close(self, timeout: float = 5.0) -> None:
        """Cierra la conexión. Espera como máximo ``timeout`` a que termine otro hilo."""
        acquired = self._lock.acquire(timeout=timeout)
        try:
            if not self._closed:
                self._conn.close()
                self._closed = True
        finally:
            if acquired:
                self._lock.release()
