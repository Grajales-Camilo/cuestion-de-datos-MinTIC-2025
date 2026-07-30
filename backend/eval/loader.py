"""Carga y valida suites golden antes de gastar cuota de un LLM (T-602).

La validación es deliberadamente estricta: una suite que no esté congelada o
que cambie la composición aprobada no puede iniciar una corrida evaluativa.
"""

from __future__ import annotations

import hashlib
import json
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
    classification: str | None = None
    input_constraints: tuple[str, ...] = ()
    selection_rule: str | None = None
    acceptable_facts: tuple[dict[str, Any], ...] = ()
    source_urls: tuple[str, ...] = ()
    observed_at: str | None = None
    data_cutoff_at: str | None = None


@dataclass(frozen=True)
class GoldenSuite:
    name: str
    version: str
    snapshot_at: str
    cases: tuple[GoldenCase, ...]
    source_path: Path
    schema_version: str = "golden-v1"


def default_suite_path(name: str, *, base_dir: Path | None = None) -> Path:
    """Resuelve el nombre público de una suite sin aceptar rutas arbitrarias."""

    allowed = {"golden-v1", "golden-v2"}
    if not name or Path(name).name != name or name not in allowed:
        raise GoldenSuiteError("Solo se admiten las suites congeladas golden-v1 y golden-v2.")
    root = base_dir or Path(__file__).resolve().parent / "golden"
    return root / f"{name}.yaml"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenSuiteError(message)


def _validate_v2_fact(case_id: str, fact: dict[str, Any], expected_ids: list[str]) -> None:
    """Valida el vocabulario cerrado de ``acceptable_facts`` de T-616B."""

    operations = {
        "quantitative": {"direct", "derived"},
        "textual": {
            "direct_text",
            "category_selection",
            "value_presence",
            "canonical_text_set",
            "argmax_label",
            "argmin_label",
        },
    }
    kind = fact.get("fact_kind")
    operation = fact.get("operation")
    _require(operation in operations.get(kind, set()), f"{case_id}: hecho aceptable inválido.")
    allowed_datasets = fact.get("allowed_datasets")
    _require(
        isinstance(allowed_datasets, list)
        and bool(allowed_datasets)
        and set(allowed_datasets) <= set(expected_ids),
        f"{case_id}: allowed_datasets inválido.",
    )
    _require(
        isinstance(fact.get("columns"), list) and bool(fact["columns"]),
        f"{case_id}: columns inválido.",
    )
    _require(
        isinstance(fact.get("input_constraints"), list),
        f"{case_id}: input_constraints de hecho inválido.",
    )
    _require(
        isinstance(fact.get("selection_rule"), str) and fact["selection_rule"].strip(),
        f"{case_id}: selection_rule de hecho inválida.",
    )
    _require(
        isinstance(fact.get("source_query"), str) and fact["source_query"].startswith("https://"),
        f"{case_id}: source_query debe ser HTTPS.",
    )
    _require(
        isinstance(fact.get("observed_at"), str) and fact["observed_at"],
        f"{case_id}: observed_at de hecho es obligatorio.",
    )
    _require(
        isinstance(fact.get("data_cutoff_at"), str) and fact["data_cutoff_at"],
        f"{case_id}: data_cutoff_at de hecho es obligatorio.",
    )
    if operation == "canonical_text_set":
        values = fact.get("value_or_set")
        cardinality = fact.get("expected_cardinality")
        _require(
            isinstance(values, list)
            and bool(values)
            and len(values) == cardinality
            and len(values) <= 50,
            f"{case_id}: canonical_text_set debe ser completo, acotado y consistente.",
        )
    if operation in {"argmax_label", "argmin_label"}:
        _require(fact.get("tie_policy") == "reject", f"{case_id}: extremo sin desempate.")


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
    schema_version = raw.get("schema_version")
    _require(
        schema_version in {"golden-v1", "golden-v2"},
        "schema_version debe ser golden-v1 o golden-v2.",
    )
    _require(suite.get("status") == "congelado", "La suite debe estar congelada.")
    _require(isinstance(suite.get("name"), str), "suite.name es obligatorio.")
    _require(isinstance(suite.get("version"), str), "suite.version es obligatorio.")
    _require(isinstance(suite.get("snapshot_at"), str), "suite.snapshot_at es obligatorio.")
    _require(
        suite.get("name") == schema_version,
        "suite.name debe coincidir con schema_version.",
    )

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
        classification = item.get("classification")
        input_constraints = item.get("input_constraints", [])
        selection_rule = item.get("selection_rule")
        acceptable_facts = item.get("acceptable_facts", [])
        source_urls = item.get("source_urls", [])
        observed_at = item.get("observed_at")
        data_cutoff_at = item.get("data_cutoff_at")
        _require(isinstance(case_id, str) and case_id, f"El caso {index} no tiene id.")
        _require(case_type in {"positive", "negative"}, f"{case_id}: case_type inválido.")
        _require(isinstance(question, str) and question.strip(), f"{case_id}: falta pregunta.")
        _require(isinstance(seed, int), f"{case_id}: seed debe ser entero.")
        _require(isinstance(notes, str) and notes.strip(), f"{case_id}: faltan notes.")
        _require(isinstance(expected_ids, list), f"{case_id}: expected_dataset_ids inválido.")
        _require(isinstance(expected_facts, list), f"{case_id}: expected_facts inválido.")
        if schema_version == "golden-v2":
            _require(
                classification in {"determined", "multi_response", "aggregate", "abstention"},
                f"{case_id}: classification inválida.",
            )
            _require(
                isinstance(input_constraints, list),
                f"{case_id}: input_constraints inválido.",
            )
            _require(
                isinstance(selection_rule, str) and selection_rule.strip(),
                f"{case_id}: selection_rule inválida.",
            )
            _require(
                isinstance(acceptable_facts, list),
                f"{case_id}: acceptable_facts inválido.",
            )
            _require(isinstance(source_urls, list), f"{case_id}: source_urls inválido.")
            _require(
                isinstance(observed_at, str) and observed_at,
                f"{case_id}: observed_at es obligatorio.",
            )
        if case_type == "positive":
            _require(
                bool(expected_ids) and bool(expected_facts),
                f"{case_id}: positivo incompleto.",
            )
            if schema_version == "golden-v2":
                _require(bool(acceptable_facts), f"{case_id}: faltan acceptable_facts.")
                _require(bool(source_urls), f"{case_id}: faltan source_urls.")
                _require(
                    isinstance(data_cutoff_at, str) and data_cutoff_at,
                    f"{case_id}: data_cutoff_at es obligatorio.",
                )
                for fact in acceptable_facts:
                    _require(isinstance(fact, dict), f"{case_id}: hecho aceptable inválido.")
                    _validate_v2_fact(case_id, fact, expected_ids)
                fact_payload = json.dumps(
                    acceptable_facts,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                fact_hash = f"sha256:{hashlib.sha256(fact_payload).hexdigest()}"
                _require(
                    f"acceptable_facts_sha256={fact_hash}" in notes,
                    f"{case_id}: huella de acceptable_facts ausente o inválida.",
                )
        else:
            _require(
                not expected_ids and not expected_facts,
                f"{case_id}: negativo no debe fijar hechos.",
            )
            if schema_version == "golden-v2":
                _require(
                    classification == "abstention" and not acceptable_facts,
                    f"{case_id}: negativo debe ser abstention sin hechos aceptables.",
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
                classification=classification,
                input_constraints=tuple(input_constraints),
                selection_rule=selection_rule,
                acceptable_facts=tuple(acceptable_facts),
                source_urls=tuple(source_urls),
                observed_at=observed_at,
                data_cutoff_at=data_cutoff_at,
            )
        )

    _require(len(cases) == 50, f"{schema_version} debe contener exactamente 50 casos.")
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
        schema_version=schema_version,
    )
