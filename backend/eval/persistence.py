"""Persistencia idempotente de una suite golden congelada (T-602)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import EvalCase, EvalSuite
from eval.loader import GoldenCase, GoldenSuite, GoldenSuiteError


@dataclass(frozen=True)
class PersistedGoldenSuite:
    suite_id: uuid.UUID
    case_ids: dict[str, uuid.UUID]


def case_signature(case: GoldenCase) -> str:
    """Huella estable del contenido que T-601 ya congeló."""

    return json.dumps(
        {
            "question": case.question,
            "case_type": case.case_type,
            "expected_dataset_ids": case.expected_dataset_ids,
            "expected_facts": case.expected_facts,
            "seed": case.seed,
            "notes": case.notes,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stored_signature(case: EvalCase) -> str:
    return json.dumps(
        {
            "question": case.question,
            "case_type": case.case_type,
            "expected_dataset_ids": tuple(case.expected_dataset_ids or []),
            "expected_facts": tuple(case.expected_facts or []),
            "seed": case.seed,
            "notes": case.notes or "",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


async def sync_golden_suite(engine: AsyncEngine, suite: GoldenSuite) -> PersistedGoldenSuite:
    """Inserta la suite/casos faltantes y rechaza cualquier mutación congelada."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        stored_suite = await session.scalar(select(EvalSuite).where(EvalSuite.name == suite.name))
        if stored_suite is None:
            stored_suite = EvalSuite(
                id=uuid.uuid4(),
                name=suite.name,
                description=f"Suite congelada cargada desde {suite.source_path.name}",
                version=suite.version,
                created_at=datetime.now(UTC),
            )
            session.add(stored_suite)
            await session.flush()
        elif stored_suite.version != suite.version:
            raise GoldenSuiteError(
                f"{suite.name} ya existe con versión {stored_suite.version}; "
                "una suite congelada no se puede reemplazar."
            )

        existing = (
            await session.scalars(select(EvalCase).where(EvalCase.suite_id == stored_suite.id))
        ).all()
        by_seed = {case.seed: case for case in existing}
        if len(by_seed) != len(existing):
            raise GoldenSuiteError("La persistencia contiene semillas repetidas para la suite.")

        case_ids: dict[str, uuid.UUID] = {}
        for case in suite.cases:
            stored_case = by_seed.get(case.seed)
            if stored_case is None:
                stored_case = EvalCase(
                    id=uuid.uuid4(),
                    suite_id=stored_suite.id,
                    question=case.question,
                    case_type=case.case_type,
                    expected_dataset_ids=list(case.expected_dataset_ids),
                    expected_facts=list(case.expected_facts),
                    seed=case.seed,
                    notes=case.notes,
                )
                session.add(stored_case)
                await session.flush()
            elif _stored_signature(stored_case) != case_signature(case):
                raise GoldenSuiteError(
                    f"La semilla {case.seed} no coincide con el golden congelado; "
                    "cree golden-v2 en lugar de editar golden-v1."
                )
            case_ids[case.case_id] = stored_case.id

        if len(existing) > len(suite.cases):
            raise GoldenSuiteError("La persistencia contiene casos ajenos a la suite congelada.")
    return PersistedGoldenSuite(suite_id=stored_suite.id, case_ids=case_ids)
