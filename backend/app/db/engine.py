from typing import Any

from pgvector.psycopg import register_vector_async
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_app_async_engine(database_url: str, **kwargs: object) -> AsyncEngine:
    engine = create_async_engine(database_url, **kwargs)
    register_pgvector_async(engine)
    return engine


def register_pgvector_async(engine: AsyncEngine) -> None:
    """Registra adaptadores pgvector en conexiones psycopg async del engine."""

    @event.listens_for(engine.sync_engine, "connect")
    def connect(dbapi_connection: Any, connection_record: object) -> None:
        del connection_record
        dbapi_connection.run_async(register_vector_async)
