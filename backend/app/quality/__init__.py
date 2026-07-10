"""Capa determinista de calidad y claims.

`pii_patterns.yaml`, `pii_classifier.py` y `eligibility.py` los introdujo
T-201 (clasificacion PII y elegibilidad de catalogo en ingesta). El nodo
determinista T6 (`validator.py`, T-401) consume `pii_risk_level`/
`eligibility_status` ya calculados por estos modulos, no los recalcula.
`cutoff.py` infiere `data_cutoff_at` sobre las filas de cada evidencia;
`placeholders.py`/`placeholders.yaml` detectan valores de relleno de forma
contextual; `messages_es.py` traduce los checks a lenguaje claro. T7
(`claims.py`) se implementa en T-403.
"""
