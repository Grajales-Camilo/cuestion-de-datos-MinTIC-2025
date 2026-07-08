"""Elegibilidad de catalogo (T-201, contracts/validacion-calidad.md §3.1, plan.md §5.3d).

Mapeo verificado contra el texto literal del contrato (linea 80): publicador
no verificado produce `diagnostic_only`, NO `blocked`. PII "unknown"/"high" y
API inactiva producen `blocked`. Precedencia: blocked > diagnostic_only >
eligible. `eligibility_reasons` acumula todos los codigos aplicables, no
solo el primero -- T5/T-401 los necesitan como lista completa de
restricciones activas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_BLOCKING_REASONS = {"api_inactive", "pii_unknown", "pii_high"}
_DIAGNOSTIC_ONLY_REASONS = {"publisher_unknown", "publisher_private"}


@dataclass
class EligibilityResult:
    eligibility_status: str
    eligibility_reasons: list[str] = field(default_factory=list)


def _derive_status(reasons: list[str]) -> str:
    if any(reason in _BLOCKING_REASONS for reason in reasons):
        return "blocked"
    if any(reason in _DIAGNOSTIC_ONLY_REASONS for reason in reasons):
        return "diagnostic_only"
    return "eligible"


def _pii_reason(pii_risk_level: str) -> str | None:
    if pii_risk_level == "unknown":
        return "pii_unknown"
    if pii_risk_level == "high":
        return "pii_high"
    if pii_risk_level == "medium":
        return "pii_medium_requires_aggregation"
    return None


def compute_dataset_eligibility(
    publisher_status: str,
    pii_risk_level: str,
    api_active: bool,
) -> EligibilityResult:
    reasons: list[str] = []

    if not api_active:
        reasons.append("api_inactive")
    if publisher_status == "unknown":
        reasons.append("publisher_unknown")
    elif publisher_status == "private_or_non_official":
        reasons.append("publisher_private")

    pii_reason = _pii_reason(pii_risk_level)
    if pii_reason is not None:
        reasons.append(pii_reason)

    return EligibilityResult(
        eligibility_status=_derive_status(reasons), eligibility_reasons=reasons
    )


def compute_column_eligibility(
    inherited_reasons: list[str],
    column_pii_risk_level: str,
) -> EligibilityResult:
    """`inherited_reasons` son los reasons de publicador/API del dataset
    (no varian por columna); esta funcion agrega el propio riesgo PII de la
    columna."""

    reasons = list(inherited_reasons)
    pii_reason = _pii_reason(column_pii_risk_level)
    if pii_reason is not None:
        reasons.append(pii_reason)

    return EligibilityResult(
        eligibility_status=_derive_status(reasons), eligibility_reasons=reasons
    )
