"""Capa determinista de calidad y claims.

`pii_patterns.yaml`, `pii_classifier.py` y `eligibility.py` los introdujo
T-201 (clasificacion PII y elegibilidad de catalogo en ingesta). El nodo
determinista T6/T7 (validacion de evidencia y claims) se implementa en
T-401/T-403 y consume `pii_risk_level`/`eligibility_status` ya calculados
por estos modulos, no los recalcula.
"""
