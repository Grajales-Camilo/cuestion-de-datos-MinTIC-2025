"""Carga y valida suites golden antes de gastar cuota de un LLM (T-602).

La validación es deliberadamente estricta: una suite que no esté congelada o
que cambie la composición aprobada no puede iniciar una corrida evaluativa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class GoldenSuiteError(ValueError):
    """La suite no cumple el contrato mínimo de T-601/T-602."""


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    case_type: str
    question: str
    expected_dataset_ids: tuple[str, ...]
    expected_facts: tuple[dict[str, Any], ...]
    seed: int
    notes: str


@dataclass(frozen=True)
class GoldenSuite:
    name: str
    version: str
    snapshot_at: str
    cases: tuple[GoldenCase, ...]
    source_path: Path


def default_suite_path(name: str, *, base_dir: Path | None = None) -> Path:
    """Resuelve el nombre público de una suite sin aceptar rutas arbitrarias."""

    if not name or Path(name).name != name or name != "golden-v1":
        raise GoldenSuiteError("Solo se admite la suite congelada golden-v1.")
    root = base_dir or Path(__file__).resolve().parent / "golden"
    return root / f"{name}.yaml"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenSuiteError(message)


def load_golden_suite(path: Path) -> GoldenSuite:
    """Lee una suite congelada y aplica las puertas estructurales de T-601."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GoldenSuiteError(f"No fue posible leer la suite golden: {exc}") from exc
    _require(isinstance(raw, dict), "La suite golden debe ser un objeto YAML.")
    suite = raw.get("suite")
    cases_raw = raw.get("cases")
    _require(isinstance(suite, dict), "Falta el bloque suite.")
    _require(isinstance(cases_raw, list), "Falta la lista cases.")
    _require(raw.get("schema_version") == "golden-v1", "schema_version debe ser golden-v1.")
    _require(suite.get("status") == "congelado", "La suite debe estar congelada.")
    _require(isinstance(suite.get("name"), str), "suite.name es obligatorio.")
    _require(isinstance(suite.get("version"), str), "suite.version es obligatorio.")
    _require(isinstance(suite.get("snapshot_at"), str), "suite.snapshot_at es obligatorio.")

    cases: list[GoldenCase] = []
    for index, item in enumerate(cases_raw, start=1):
        _require(isinstance(item, dict), f"El caso {index} no es un objeto.")
        case_id = item.get("id")
        case_type = item.get("case_type")
        question = item.get("question")
        seed = item.get("seed")
        notes = item.get("notes")
        expected_ids = item.get("expected_dataset_ids", [])
        expected_facts = item.get("expected_facts", [])
        _require(isinstance(case_id, str) and case_id, f"El caso {index} no tiene id.")
        _require(case_type in {"positive", "negative"}, f"{case_id}: case_type inválido.")
        _require(isinstance(question, str) and question.strip(), f"{case_id}: falta pregunta.")
        _require(isinstance(seed, int), f"{case_id}: seed debe ser entero.")
        _require(isinstance(notes, str) and notes.strip(), f"{case_id}: faltan notes.")
        _require(isinstance(expected_ids, list), f"{case_id}: expected_dataset_ids inválido.")
        _require(isinstance(expected_facts, list), f"{case_id}: expected_facts inválido.")
        if case_type == "positive":
            _require(
                bool(expected_ids) and bool(expected_facts),
                f"{case_id}: positivo incompleto.",
            )
        else:
            _require(
                not expected_ids and not expected_facts,
                f"{case_id}: negativo no debe fijar hechos.",
            )
        cases.append(
            GoldenCase(
                case_id=case_id,
                case_type=case_type,
                question=question,
                expected_dataset_ids=tuple(expected_ids),
                expected_facts=tuple(expected_facts),
                seed=seed,
                notes=notes,
            )
        )

    _require(len(cases) == 50, "golden-v1 debe contener exactamente 50 casos.")
    _require(
        sum(case.case_type == "positive" for case in cases) == 40,
        "Deben existir 40 positivos.",
    )
    _require(
        sum(case.case_type == "negative" for case in cases) == 10,
        "Deben existir 10 negativos.",
    )
    _require(len({case.case_id for case in cases}) == len(cases), "Hay IDs de caso repetidos.")
    _require(len({case.seed for case in cases}) == len(cases), "Hay semillas repetidas.")
    return GoldenSuite(
        name=suite["name"],
        version=suite["version"],
        snapshot_at=suite["snapshot_at"],
        cases=tuple(cases),
        source_path=path,
    )
