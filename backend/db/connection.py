"""
Conexión SQLite asincrona para el debate-arena.

Estrategia: una sola connection persistente con WAL mode. aiosqlite serializa
todas las queries en un thread interno, asi que esto es seguro frente a
concurrencia y nunca bloquea el event loop por mucho tiempo.

El schema se aplica idempotente al inicializar.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)


_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Wrapper sobre aiosqlite con init/close idempotente."""

    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        """Abre la connection (idempotente) y aplica el schema."""
        async with self._lock:
            if self._conn is not None:
                return self._conn

            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self.path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA synchronous = NORMAL;")

            schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
            await conn.executescript(schema_sql)
            await conn.commit()

            self._conn = conn
            logger.info("sqlite connected at %s", self.path)
            return conn

    async def close(self):
        async with self._lock:
            if self._conn is not None:
                try:
                    await self._conn.close()
                except Exception:
                    logger.exception("failed to close db connection")
                self._conn = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn


# Singleton global. Lo inicializa el lifespan de FastAPI.
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(config.DB_PATH)
    return _db


async def init_db() -> Database:
    db = get_db()
    await db.connect()
    return db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None
