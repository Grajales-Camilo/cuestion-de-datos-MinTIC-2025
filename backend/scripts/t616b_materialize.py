"""Materializa y verifica la suite normativa golden-v2 (T-616B, RF-601/602).

La entrada es la auditoría T-616A-R aprobada. ``--write`` y ``--check`` son
locales; ``--verify-live`` reproduce las proyecciones contra las fuentes
oficiales por HTTPS. El script no escribe en PostgreSQL ni ejecuta el agente.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml

from eval.loader import load_golden_suite

BACKEND = Path(__file__).resolve().parents[1]
AUDIT_PATH = BACKEND / "eval" / "reports" / "t616a-case-audit.json"
GOLDEN_V1_PATH = BACKEND / "eval" / "golden" / "golden-v1.yaml"
GOLDEN_V2_PATH = BACKEND / "eval" / "golden" / "golden-v2.yaml"

GOLDEN_V1_SHA256 = "ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72"
POSTAL_CANONICAL_SOURCE = (
    "https://visor.codigopostal.gov.co/472/visor/Codigos_Postales_Nacionales.csv"
)
POSTAL_CANONICAL_SOURCE_SHA256 = (
    "sha256:fdfd886f58b904ff29236eaf24acabdc999cc4fd2992493a8c3d0bc2b52241c7"
)

ALLOWED_CLASSIFICATIONS = {
    "determined",
    "multi_response",
    "aggregate",
    "abstention",
}
ALLOWED_CHANGE_TYPES = {"retain", "clarify", "rewrite"}
ALLOWED_FACT_OPERATIONS = {
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

COUNT_QUERY_OVERRIDES = {
    "pilot-015-puestos-electorales": {
        "$select": "count(distinct puesto) AS n",
        "$where": "municipio='MEDELLIN'",
    },
    "pilot-033-gas-natural-vehicular": {
        "$select": "count(*) AS n",
        "$where": "anio_venta='2025' AND mes_venta='09'",
    },
    "pilot-037-calidad-aire": {
        "$select": "count(distinct id_estacion) AS n",
        "$where": "autoridad_ambiental='AMVA'",
    },
}

GROUPED_EXPECTATIONS = {
    "pilot-036-delitos-sexuales": [
        {"departamento": "ANTIOQUIA", "n": "5"},
        {"departamento": "ATLANTICO", "n": "1"},
        {"departamento": "BOGOTA D.C.", "n": "4"},
        {"departamento": "BOYACA", "n": "3"},
        {"departamento": "CASANARE", "n": "1"},
        {"departamento": "CESAR", "n": "1"},
        {"departamento": "CUNDINAMARCA", "n": "5"},
        {"departamento": "HUILA", "n": "2"},
        {"departamento": "MAGDALENA", "n": "2"},
        {"departamento": "META", "n": "5"},
        {"departamento": "NARIÑO", "n": "2"},
        {"departamento": "RISARALDA", "n": "2"},
        {"departamento": "SANTANDER", "n": "2"},
        {"departamento": "VALLE DEL CAUCA", "n": "2"},
    ]
}

POSTAL_CANONICAL_VALUES = {
    "Urbano": "153420",
    "Rural": "153427",
}

RAW_EXPECTED_VALUE_OVERRIDES = {
    "pilot-004-justicia-presupuesto": {
        "apropiaci_n_vigente": "4,526,836,158,739.00",
        "pagos": "3,233,457,359,631.73",
    },
    "pilot-013-app-dnp": {
        "tipo_app": "Iniciativa Privada sin Recursos Públicos",
        "nombre_proyecto": "IP Ibagué - Cajamarca",
    },
    "pilot-034-fncer": {"tipo": "Eólico"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: se esperaba un objeto YAML")
    return loaded


def _case_short_id(case_id: str) -> str:
    match = re.match(r"pilot-(\d{3})-", case_id)
    if not match:
        raise ValueError(f"ID no canónico: {case_id}")
    return f"pilot-{match.group(1)}"


def _full_source_url(dataset_id: str, source_query: str) -> str:
    if source_query.startswith("https://"):
        return source_query
    query = source_query.removeprefix("?")
    return f"https://www.datos.gov.co/resource/{dataset_id}.json?{query}"


def _query_url(dataset_id: str, query: dict[str, str]) -> str:
    encoded = urlencode(query, safe="()',*")
    return f"https://www.datos.gov.co/resource/{dataset_id}.json?{encoded}"


def _clean_text_value(value: Any) -> str:
    text = str(value)
    text = re.sub(r"\s+\((?:obs\.|etiqueta estable).*?\)\s*$", "", text)
    return text.strip()


def _numeric_value(value: Any) -> str:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(" ", ""))
    if not match:
        raise ValueError(f"No se pudo extraer un valor numérico de {value!r}")
    return match.group(0)


def _expected_facts_for(
    case: dict[str, Any],
    fact: dict[str, Any],
) -> list[dict[str, Any]]:
    case_id = str(case["case_id"])
    dataset_id = str(case["expected_dataset_ids"][0])
    source_url = _full_source_url(dataset_id, str(fact["source_query"]))
    tolerance = fact.get("tolerance", 0) or 0

    projected_facts: list[dict[str, Any]]
    if case_id in GROUPED_EXPECTATIONS and fact["fact_kind"] == "quantitative":
        source_url = _query_url(
            dataset_id,
            {
                "$select": "departamento,count(*) AS n",
                "$where": "fecha_hecho='2026-05-31T00:00:00.000'",
                "$group": "departamento",
                "$order": "departamento",
            },
        )
        projected_facts = [
            {
                "description": "Conteo agregado por departamento, sin filas individuales.",
                "source_url": source_url,
                "expected_value": row,
                "tolerance": tolerance,
            }
            for row in GROUPED_EXPECTATIONS[case_id]
        ]
    elif fact["fact_kind"] == "textual":
        operation = fact["operation"]
        if operation == "canonical_text_set":
            values = fact["value_or_set"]
            if not isinstance(values, list):
                raise ValueError(f"{case_id}: canonical_text_set sin lista")
            column = str(fact["columns"][0])
            projected_facts = [
                {
                    "description": f"{column} pertenece al conjunto canónico completo.",
                    "source_url": source_url,
                    "expected_value": {column: value},
                    "tolerance": 0,
                }
                for value in values
            ]
        else:
            column = str(fact.get("label_column") or fact["columns"][0])
            value = _clean_text_value(fact["value_or_set"])
            projected_facts = [
                {
                    "description": f"{operation} verificado para {column}.",
                    "source_url": source_url,
                    "expected_value": {column: value},
                    "tolerance": 0,
                }
            ]
    else:
        value = fact["value_or_set"]
        columns = [str(item) for item in fact["columns"]]
        if isinstance(value, list):
            if len(value) != len(columns):
                raise ValueError(f"{case_id}: valores cuantitativos no alineados con columnas")
            expected_value = dict(zip(columns, value, strict=True))
        else:
            output_column = columns[0]
            if fact["operation"] == "derived":
                output_column = "metric_value"
                formula = fact.get("formula") or {}
                if formula.get("op") == "count":
                    output_column = "n"
            expected_value = {output_column: _numeric_value(value)}

        if case_id in COUNT_QUERY_OVERRIDES:
            source_url = _query_url(dataset_id, COUNT_QUERY_OVERRIDES[case_id])
        projected_facts = [
            {
                "description": f"{fact['operation']} cuantitativo verificado.",
                "source_url": source_url,
                "expected_value": expected_value,
                "tolerance": tolerance,
            }
        ]

    for projected in projected_facts:
        for key, value in RAW_EXPECTED_VALUE_OVERRIDES.get(case_id, {}).items():
            if key in projected["expected_value"]:
                projected["expected_value"][key] = value
    return projected_facts


def _v2_classification(case: dict[str, Any]) -> str:
    if case["case_type"] == "negative":
        return "abstention"
    facts = case["proposed_acceptable_facts"]
    if case["case_id"] == "pilot-016-codigos-postales":
        return "multi_response"
    if any(f["operation"] == "canonical_text_set" for f in facts):
        return "multi_response"
    if any(f["fact_kind"] == "quantitative" and f["operation"] == "derived" for f in facts):
        return "aggregate"
    return "determined"


def _approved_fact(case: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(fact)
    result.pop("note", None)
    result["source_query"] = _full_source_url(
        str(case["expected_dataset_ids"][0]),
        str(result["source_query"]),
    )
    if case["case_id"] == "pilot-016-codigos-postales":
        kind = "Urbano" if "tipo=Urbano" in result["input_constraints"] else "Rural"
        result["canonical_value"] = POSTAL_CANONICAL_VALUES[kind]
        result["canonical_source"] = POSTAL_CANONICAL_SOURCE
        result["canonical_source_hash"] = POSTAL_CANONICAL_SOURCE_SHA256
        result["selection_rule"] = (
            f"fila única de tipo {kind}; conservar el valor publicado por Socrata "
            "y reportar su forma canónica oficial de seis dígitos"
        )
    return result


def _positive_case(case: dict[str, Any]) -> dict[str, Any]:
    acceptable_facts = [_approved_fact(case, fact) for fact in case["proposed_acceptable_facts"]]
    expected_facts = [
        projected for fact in acceptable_facts for projected in _expected_facts_for(case, fact)
    ]
    digest = _canonical_json_hash(acceptable_facts)
    question = str(case["golden_v2_question_proposal"])
    if case["case_id"] == "pilot-016-codigos-postales":
        question = (
            "¿Qué códigos postales publica la fuente para las zonas urbana y rural "
            "de Rondón, Boyacá, conservando el formato original y aclarando su forma "
            "canónica oficial de seis dígitos?"
        )
    notes = f"T-616B: {case['question_change_rationale']} acceptable_facts_sha256={digest}"
    source_urls = sorted(
        {
            *case["source_urls"],
            *(fact["source_query"] for fact in acceptable_facts),
        }
    )
    if case["case_id"] == "pilot-016-codigos-postales":
        source_urls.append(POSTAL_CANONICAL_SOURCE)
        source_urls = sorted(set(source_urls))
    input_constraints = list(
        dict.fromkeys(
            str(constraint) for fact in acceptable_facts for constraint in fact["input_constraints"]
        )
    )
    return {
        "id": case["case_id"],
        "case_type": "positive",
        "classification": _v2_classification(case),
        "question": question,
        "question_change": case["question_change"],
        "question_change_rationale": case["question_change_rationale"],
        "expected_dataset_ids": case["expected_dataset_ids"],
        "input_constraints": input_constraints,
        "selection_rule": "; ".join(str(fact["selection_rule"]) for fact in acceptable_facts),
        "acceptable_facts": acceptable_facts,
        "expected_facts": expected_facts,
        "source_urls": source_urls,
        "observed_at": case["evidence"].get("manifest_ref") and acceptable_facts[0]["observed_at"],
        "data_cutoff_at": case["data_cutoff_at"],
        "seed": case["seed"],
        "notes": notes,
    }


def _negative_case(case: dict[str, Any], v1_case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["case_id"],
        "case_type": "negative",
        "classification": "abstention",
        "question": case["question_v1"],
        "question_change": "retain",
        "question_change_rationale": "La guarda negativa de golden-v1 sigue vigente.",
        "expected_dataset_ids": [],
        "input_constraints": [],
        "selection_rule": f"abstain:{case['incapacity_class']}",
        "acceptable_facts": [],
        "expected_facts": [],
        "source_urls": [],
        "observed_at": "2026-07-18",
        "data_cutoff_at": None,
        "seed": case["seed"],
        "notes": v1_case["notes"],
    }


def build_suite() -> dict[str, Any]:
    if _sha256(GOLDEN_V1_PATH) != GOLDEN_V1_SHA256:
        raise ValueError("golden-v1 cambió: T-616B se detiene")
    audit = _load_json(AUDIT_PATH)
    v1 = _load_yaml(GOLDEN_V1_PATH)
    audit_cases = {case["case_id"]: case for case in audit["cases"]}
    v1_cases = {case["id"]: case for case in v1["cases"]}
    if set(audit_cases) != set(v1_cases):
        raise ValueError("La auditoría y golden-v1 no contienen los mismos 50 IDs")

    cases: list[dict[str, Any]] = []
    for v1_case in v1["cases"]:
        audited = audit_cases[v1_case["id"]]
        if audited["case_type"] == "positive":
            cases.append(_positive_case(audited))
        else:
            cases.append(_negative_case(audited, v1_case))

    return {
        "schema_version": "golden-v2",
        "suite": {
            "name": "golden-v2",
            "version": "2.0.0",
            "status": "congelado",
            "snapshot_at": "2026-07-18",
            "description": (
                "Suite normativa T-616B: 50 casos aprobados a partir de la auditoría "
                "T-616A-R, con hechos aceptables tipados, restricciones explícitas y "
                "fuentes reproducibles. golden-v1 permanece intacto."
            ),
            "requirements": ["RF-601", "RF-602"],
            "approval": {
                "authorized_at": "2026-07-18",
                "authorization": "Instrucción humana: «Continúa con la siguiente tarea».",
                "coordinator_decision": (
                    "Se aprueban las propuestas concretas auditadas; 038/039 se "
                    "reescriben y 016 se resuelve con el CSV oficial de 4-72."
                ),
            },
            "source_audit": {
                "schema_version": audit["schema_version"],
                "path": "eval/reports/t616a-case-audit.json",
                "sha256": f"sha256:{_sha256(AUDIT_PATH)}",
            },
            "golden_v1_sha256": f"sha256:{GOLDEN_V1_SHA256}",
        },
        "cases": cases,
    }


def validate_suite(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cases = raw.get("cases")
    if raw.get("schema_version") != "golden-v2":
        errors.append("schema_version debe ser golden-v2")
    if not isinstance(cases, list) or len(cases) != 50:
        return [*errors, "golden-v2 debe contener exactamente 50 casos"]
    if sum(case.get("case_type") == "positive" for case in cases) != 40:
        errors.append("golden-v2 debe contener 40 positivos")
    if sum(case.get("case_type") == "negative" for case in cases) != 10:
        errors.append("golden-v2 debe contener 10 negativos")
    if len({case.get("id") for case in cases}) != 50:
        errors.append("IDs repetidos")
    if len({case.get("seed") for case in cases}) != 50:
        errors.append("semillas repetidas")

    for case in cases:
        case_id = str(case.get("id"))
        if case.get("classification") not in ALLOWED_CLASSIFICATIONS:
            errors.append(f"{case_id}: classification inválida")
        if case.get("question_change") not in ALLOWED_CHANGE_TYPES:
            errors.append(f"{case_id}: question_change inválido")
        if not case.get("question") or not case.get("selection_rule"):
            errors.append(f"{case_id}: pregunta/regla de selección ausente")
        if not isinstance(case.get("input_constraints"), list):
            errors.append(f"{case_id}: input_constraints inválido")
        if case["case_type"] == "negative":
            if (
                case.get("expected_dataset_ids")
                or case.get("acceptable_facts")
                or case.get("expected_facts")
            ):
                errors.append(f"{case_id}: negativo contiene hechos")
            continue
        required = (
            "expected_dataset_ids",
            "acceptable_facts",
            "expected_facts",
            "source_urls",
            "observed_at",
            "data_cutoff_at",
        )
        if any(not case.get(field) for field in required):
            errors.append(f"{case_id}: positivo incompleto")
        if "acceptable_facts_sha256=sha256:" not in case.get("notes", ""):
            errors.append(f"{case_id}: falta huella de acceptable_facts")
        else:
            expected_digest = _canonical_json_hash(case["acceptable_facts"])
            if f"acceptable_facts_sha256={expected_digest}" not in case["notes"]:
                errors.append(f"{case_id}: huella de acceptable_facts no coincide")
        for fact in case.get("acceptable_facts", []):
            kind = fact.get("fact_kind")
            operation = fact.get("operation")
            if operation not in ALLOWED_FACT_OPERATIONS.get(kind, set()):
                errors.append(f"{case_id}: combinación fact_kind/operation inválida")
            if not set(fact.get("allowed_datasets", [])) <= set(case["expected_dataset_ids"]):
                errors.append(f"{case_id}: hecho referencia dataset no esperado")
            if not str(fact.get("source_query", "")).startswith("https://"):
                errors.append(f"{case_id}: source_query no absoluta")
            if operation == "canonical_text_set":
                values = fact.get("value_or_set")
                if (
                    not isinstance(values, list)
                    or not values
                    or len(values) != fact.get("expected_cardinality")
                    or len(values) > 50
                ):
                    errors.append(f"{case_id}: conjunto canónico inválido")
            if operation in {"argmax_label", "argmin_label"} and fact.get("tie_policy") != "reject":
                errors.append(f"{case_id}: extremo sin tie_policy=reject")
        payload = json.dumps(case, ensure_ascii=False).lower()
        if "<…" in payload or '"value_or_set": "a determinar"' in payload:
            errors.append(f"{case_id}: contiene placeholder")
    return errors


def write_suite() -> None:
    raw = build_suite()
    errors = validate_suite(raw)
    if errors:
        raise ValueError("\n".join(errors))
    GOLDEN_V2_PATH.write_text(
        yaml.safe_dump(
            raw,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        ),
        encoding="utf-8",
    )
    load_golden_suite(GOLDEN_V2_PATH)


def check_suite() -> None:
    expected = build_suite()
    actual = _load_yaml(GOLDEN_V2_PATH)
    errors = validate_suite(actual)
    if errors:
        raise ValueError("\n".join(errors))
    if actual != expected:
        raise ValueError("golden-v2.yaml no coincide con la materialización canónica")
    load_golden_suite(GOLDEN_V2_PATH)


def _values_match(actual: Any, expected: Any, tolerance: float) -> bool:
    if str(actual) == str(expected):
        return True
    try:
        return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal(str(tolerance))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _row_matches(row: dict[str, Any], expected: dict[str, Any], tolerance: float) -> bool:
    return all(
        key in row and _values_match(row[key], value, tolerance) for key, value in expected.items()
    )


def verify_live() -> None:
    """Reproduce las proyecciones normativas contra las fuentes oficiales."""

    check_suite()
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"dependencia faltante: {exc}") from exc

    raw = _load_yaml(GOLDEN_V2_PATH)
    errors: list[str] = []
    cache: dict[str, list[dict[str, Any]]] = {}
    headers = {"User-Agent": "cuestion-de-datos-t616b-verifier/1.0"}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=90) as client:
        postal_response = client.get(POSTAL_CANONICAL_SOURCE)
        postal_response.raise_for_status()
        postal_hash = f"sha256:{hashlib.sha256(postal_response.content).hexdigest()}"
        if postal_hash != POSTAL_CANONICAL_SOURCE_SHA256:
            errors.append("pilot-016: cambió el hash del CSV oficial de códigos postales")
        postal_text = postal_response.content.decode("utf-8-sig")
        for expected_line in (
            ",15,BOYACA,15621,RONDON,1534,153420,",
            ",15,BOYACA,15621,RONDON,1534,153427,",
        ):
            if expected_line not in postal_text:
                errors.append(f"pilot-016: el CSV oficial no contiene {expected_line}")

        for case in raw["cases"]:
            case_id = case["id"]
            for fact in case["expected_facts"]:
                url = fact["source_url"]
                if url not in cache:
                    response = client.get(url)
                    if response.status_code != 200:
                        errors.append(f"{case_id}: HTTP {response.status_code} en {url}")
                        cache[url] = []
                        continue
                    payload = response.json()
                    cache[url] = payload if isinstance(payload, list) else [payload]
                expected = fact["expected_value"]
                tolerance = float(fact.get("tolerance", 0) or 0)
                if not any(_row_matches(row, expected, tolerance) for row in cache[url]):
                    errors.append(f"{case_id}: hecho no reproducible en {url}: {expected}")

            for fact in case["acceptable_facts"]:
                if fact["operation"] != "canonical_text_set":
                    continue
                url = fact["source_query"]
                if url not in cache:
                    response = client.get(url)
                    if response.status_code != 200:
                        errors.append(f"{case_id}: HTTP {response.status_code} en {url}")
                        cache[url] = []
                        continue
                    payload = response.json()
                    cache[url] = payload if isinstance(payload, list) else [payload]
                column = fact["columns"][0]
                actual = sorted(
                    {
                        str(row[column])
                        for row in cache[url]
                        if isinstance(row, dict) and row.get(column) is not None
                    }
                )
                expected = sorted(str(value) for value in fact["value_or_set"])
                if actual != expected:
                    errors.append(f"{case_id}: canonical_text_set no coincide con la fuente")
    if errors:
        raise ValueError("\n".join(errors))
    print(
        "OK: 40/40 positivos y 128 proyecciones esperadas reproducidos "
        f"en {len(cache)} consultas oficiales únicas"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--verify-live", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_suite()
        print(f"OK: materializado {GOLDEN_V2_PATH}")
    elif args.check:
        check_suite()
        print("OK: golden-v2 coincide con la auditoría aprobada y pasa sus validadores")
    else:
        verify_live()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
