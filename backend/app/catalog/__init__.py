"""Ingesta del catalogo de datos.gov.co (T-201, plan.md §5).

Aislado de `app/tools/` deliberadamente: `app/tools/` (T-302) son las
UNICAS herramientas invocables por el enrutador LLM (contracts/agent-tools.md);
la ingesta masiva del catalogo es un proceso batch, no invocado por el LLM.
"""
