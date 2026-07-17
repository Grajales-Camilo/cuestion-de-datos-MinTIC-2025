"""Guardia T-612 (research.md §25, pruebas.md §4.4).

Falla si `tests/integration/test_deterministic_agent_acceptance.py` importa
`app.agent.graph`, `build_graph` o `initial_state` — símbolos exclusivos del
runtime legado congelado. Análisis estático del árbol de sintaxis (sin
importar el módulo, sin red, sin PostgreSQL): detecta la superficie real de
imports declarados, sin falsos positivos por menciones en docstrings o
comentarios (que sí nombran esos símbolos a propósito, para documentar la
regla).

Ronda de revisión (corrección al hallazgo "la guardia puede eludirse
importando un helper que a su vez ejecute el legado"): el análisis ahora es
**transitivo** — si el archivo de aceptación llegara a importar un helper de
otro módulo `tests.*`, ese módulo también se analiza recursivamente — y
también detecta **imports dinámicos** (`importlib.import_module("app.agent
.graph")`, `__import__("app.agent.graph")`) con el nombre del módulo/símbolo
prohibido como literal de cadena, no solo `import`/`from ... import` estáticos.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS_ROOT = Path(__file__).parent
_TARGET = _TESTS_ROOT / "integration" / "test_deterministic_agent_acceptance.py"
_FORBIDDEN_MODULES = {"app.agent.graph"}
_FORBIDDEN_NAMES = {"build_graph", "initial_state"}
_FORBIDDEN_STRING_NEEDLES = {"app.agent.graph", "build_graph", "initial_state"}


def _statically_imported_modules_and_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            names.update(alias.name for alias in node.names)
    return modules, names


def _local_test_module_imports(tree: ast.Module) -> set[str]:
    """Módulos `tests.*` de este mismo repositorio importados por el archivo,
    candidatos a analizarse transitivamente (podrían reexportar o ejecutar el
    legado sin que el archivo de aceptación lo importe directamente)."""

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tests."):
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(
                alias.name for alias in node.names if alias.name.startswith("tests.")
            )
    return modules


def _dynamic_import_string_literals(tree: ast.Module) -> set[str]:
    """Detecta `importlib.import_module("...")` / `__import__("...")` con un
    literal de cadena — el mecanismo que elude la detección de `ast.Import`/
    `ast.ImportFrom` porque el nombre del módulo nunca aparece como tal."""

    literals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_import_call = (isinstance(func, ast.Name) and func.id == "__import__") or (
            isinstance(func, ast.Attribute) and func.attr == "import_module"
        )
        if not is_import_call:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                literals.add(arg.value)
    return literals


def _module_name_to_path(module_name: str) -> Path:
    relative = module_name.removeprefix("tests.").replace(".", "/") + ".py"
    return _TESTS_ROOT / relative


def _analyze_recursively(
    path: Path, *, seen: set[Path] | None = None
) -> tuple[set[str], set[str], set[str]]:
    """Analiza `path` y, transitivamente, cualquier módulo `tests.*` que
    importe. Devuelve (módulos importados, nombres importados, literales de
    import dinámico) acumulados de todo el árbol de imports locales."""

    if seen is None:
        seen = set()
    resolved = path.resolve()
    if resolved in seen or not path.is_file():
        return set(), set(), set()
    seen.add(resolved)

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules, names = _statically_imported_modules_and_names(tree)
    dynamic_literals = _dynamic_import_string_literals(tree)

    for local_module in _local_test_module_imports(tree):
        sub_modules, sub_names, sub_dynamic = _analyze_recursively(
            _module_name_to_path(local_module), seen=seen
        )
        modules |= sub_modules
        names |= sub_names
        dynamic_literals |= sub_dynamic

    return modules, names, dynamic_literals


def test_deterministic_acceptance_file_exists() -> None:
    assert _TARGET.is_file(), f"no existe {_TARGET} — T-611 debe crearlo primero"


def test_deterministic_acceptance_never_imports_legacy_graph_symbols() -> None:
    modules, names, _dynamic = _analyze_recursively(_TARGET)

    forbidden_modules = modules & _FORBIDDEN_MODULES
    forbidden_names = names & _FORBIDDEN_NAMES

    assert not forbidden_modules, (
        f"la aceptación determinista no puede importar {forbidden_modules} "
        "(runtime legado congelado, research.md §25)"
    )
    assert not forbidden_names, (
        f"la aceptación determinista no puede importar {forbidden_names} "
        "(símbolos exclusivos de app.agent.graph)"
    )


def test_deterministic_acceptance_has_no_dynamic_import_of_legacy_graph() -> None:
    """Cierra la elusión por `importlib.import_module`/`__import__` con el
    nombre del módulo legado como literal de cadena, en el archivo de
    aceptación y en cualquier helper local `tests.*` que importe
    transitivamente."""

    _modules, _names, dynamic_literals = _analyze_recursively(_TARGET)

    offending = {
        literal
        for literal in dynamic_literals
        if any(needle in literal for needle in _FORBIDDEN_STRING_NEEDLES)
    }
    assert not offending, (
        f"import dinámico del runtime legado detectado: {offending} "
        "(importlib.import_module/__import__ con app.agent.graph como literal)"
    )


def test_deterministic_acceptance_enters_through_the_deterministic_runtime() -> None:
    """Confirma la superficie positiva exigida por pruebas.md §4.4: la suite
    debe entrar por `execute_deterministic_agent_run_async`, no reimplementar
    ni sustituir esa entrada por `run_deterministic_agent` directamente."""

    _modules, names, _dynamic = _analyze_recursively(_TARGET)

    assert "execute_deterministic_agent_run_async" in names
