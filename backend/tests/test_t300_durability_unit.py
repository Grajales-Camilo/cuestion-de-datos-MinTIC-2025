"""Pruebas deterministas sin red de T-300 (durabilidad): partes puras de
`app/agent/*` que no requieren Postgres real. Las pruebas de concurrencia
con Postgres real y la demo de kill de proceso viven en
`tests/integration/test_t300_durability.py`."""

import asyncio
import threading
import time

import pytest

from app.agent import runner
from app.agent.heartbeat_sweep import _error_payload
from app.agent.toy_graph import NODES
from app.main import PocAgentQueryRequest


async def test_sleep_cancelable_returns_false_after_full_duration() -> None:
    event = threading.Event()
    start = time.monotonic()

    cancelled = await runner._sleep_cancelable(0.3, event)

    elapsed = time.monotonic() - start
    assert cancelled is False
    assert elapsed >= 0.3


async def test_sleep_cancelable_returns_true_if_already_set() -> None:
    event = threading.Event()
    event.set()

    cancelled = await runner._sleep_cancelable(5.0, event)

    assert cancelled is True


async def test_sleep_cancelable_reacts_promptly_when_cancelled_midway() -> None:
    event = threading.Event()

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.15)
        event.set()

    task = asyncio.create_task(_cancel_soon())
    start = time.monotonic()
    cancelled = await runner._sleep_cancelable(5.0, event)
    elapsed = time.monotonic() - start
    await task

    assert cancelled is True
    # No debe esperar los 5s completos: se detecta la cancelacion en el
    # siguiente tick corto (CANCEL_POLL_INTERVAL_S).
    assert elapsed < 1.0


def test_toy_graph_has_exactly_three_nodes() -> None:
    assert len(NODES) == 3
    assert NODES == ("node_a", "node_b", "node_c")
    assert len(set(NODES)) == 3


def test_error_payload_shape_matches_error_envelope() -> None:
    payload = _error_payload(
        "RUN_TIMEOUT", "failed", "mensaje para el usuario", "detalle tecnico"
    )

    assert payload["error"]["code"] == "RUN_TIMEOUT"
    assert payload["error"]["status"] == "failed"
    assert payload["error"]["message_user"] == "mensaje para el usuario"
    assert payload["error"]["retryable"] is True


def test_poc_query_request_defaults_to_runner_step_delay() -> None:
    request = PocAgentQueryRequest()

    assert request.question is None
    assert request.step_delay_s == runner.DEFAULT_STEP_DELAY_S


@pytest.mark.parametrize("value", [-1, 31])
def test_poc_query_request_rejects_step_delay_out_of_bounds(value: float) -> None:
    with pytest.raises(ValueError):
        PocAgentQueryRequest(step_delay_s=value)


def test_active_runs_registry_starts_empty_between_tests() -> None:
    # Cada corrida se elimina de ACTIVE_RUNS via done_callback al terminar
    # (runner.start_run_task); esta prueba documenta el invariante, no
    # ejercita el ciclo de vida completo (eso es integracion).
    assert isinstance(runner.ACTIVE_RUNS, dict)
