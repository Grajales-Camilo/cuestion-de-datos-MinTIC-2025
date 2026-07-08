import asyncio
import sys
from collections.abc import Awaitable, Callable

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import Settings


async def setup_checkpointer(settings: Settings) -> None:
    """Inicializa idempotentemente tablas de checkpoints de LangGraph (RF-209)."""

    if sys.platform == "win32":
        await asyncio.to_thread(_run_with_selector_loop, _setup_checkpointer_async, settings)
        return
    await _setup_checkpointer_async(settings)


async def _setup_checkpointer_async(settings: Settings) -> None:
    async with AsyncPostgresSaver.from_conn_string(settings.psycopg_database_url) as saver:
        await saver.setup()


def _run_with_selector_loop(
    async_fn: Callable[[Settings], Awaitable[None]],
    settings: Settings,
) -> None:
    asyncio.run(async_fn(settings), loop_factory=asyncio.SelectorEventLoop)
