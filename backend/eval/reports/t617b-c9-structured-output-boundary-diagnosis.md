# T-617B-C9 — Diagnóstico de la frontera de salida estructurada

## Estado

`SMOKE_FAILED` / `FULL_GATE_BLOCKED` /
`READY_FOR_STRUCTURED_OUTPUT_BOUNDARY_FIX`

- Smoke: `1aca0753-0db3-4b7c-81e6-3a46e8a101f5`
- Commit evaluado: `fd6cc70b595dad31862d8ca296c1edc1728491ff`
- Suite: `golden-v2`
- Runtime: `deterministic`
- Proveedor/modelo: `google/gemini-2.5-flash`
- Hechos textuales: habilitados

## Resultado verificable

- 10/10 casos canónicos, sin duplicados.
- Positivos: 2/8 (`pilot-003` y `pilot-013`).
- Negativos: 2/2.
- `pilot-013` confirma C8/C8A en el smoke formal.
- Fabricaciones: 0.
- Cifras huérfanas: 0.
- Integridad de claims/hechos aplicables: 100%.
- Socrata observable: 3/3.
- Corridas `running` al finalizar: 0.
- Cinco casos quedaron reportados como infraestructura:
  `pilot-002`, `pilot-005`, `pilot-012`, `pilot-021` y `pilot-038`.
- `pilot-022` ejecutó consulta pero no coincidió con `expected_facts`;
  permanece indeterminado para revisión separada.

El primer intento de lanzar el smoke no ejecutó casos ni gastó cuota: PowerShell
no transmitió los `--case-id` repetidos al proceso hijo y el preflight rechazó
la selección completa de 50. El comando formal corregido sí ejecutó exactamente
los diez canónicos.

## Causa raíz de los cinco falsos fallos de infraestructura

Las cinco corridas tienen `terminal_error_code=LLM_PROVIDER_ERROR`, pero sus
eventos terminales prueban que Gemini sí respondió. El error real fue validar
su respuesta contra `EnumeratedPlanSelection`:

- cuatro respuestas incluyeron texto explicativo libre dentro de
  `textual_requests`, que solo admite objetos `TextualSelection`;
- `pilot-005` propuso tres métricas con `operation="lookup"`, representación
  rechazada porque un `LOOKUP` debe usar `dimension_column_indexes`.

`ainvoke_structured_chat_model` agotó su reparación y lanzó
`LLMStructuredOutputError`, subclase de `LLMProviderError`. El runner
determinista captura la clase padre y persiste siempre
`LLM_PROVIDER_ERROR`. Esto contradice el contrato ya documentado:
`STRUCTURED_OUTPUT_INVALID` es fallo del contrato de ejecución del agente, no
caída de red/cuota/5xx del proveedor.

Por tanto:

1. el arnés no inventó la clasificación; leyó fielmente un terminal mal
   tipado por el runtime;
2. corregir solo la clasificación hará el reporte honesto, pero no permitirá
   que los casos completen;
3. habilitar hechos textuales expuso una incompatibilidad sistemática entre el
   esquema ampliado y salidas frecuentes del planificador.

## Incremento siguiente acotado

1. En el runner determinista, capturar `LLMStructuredOutputError` antes que
   `LLMProviderError` y persistir `STRUCTURED_OUTPUT_INVALID`,
   `owner=agent`, no reintentable como infraestructura.
2. En la frontera del contrato del planificador, tolerar únicamente
   representaciones opcionales semánticamente recuperables:
   - descartar entradas no estructuradas de `textual_requests` sin convertir su
     texto en hechos;
   - para operación superior `LOOKUP`, trasladar índices de métricas
     `operation="lookup"` a `dimension_column_indexes`, sin inventar columnas,
     filtros, valores ni operaciones.
3. Mantener rechazo estricto para cualquier otra forma inválida.
4. Probar ambos caminos con payloads reales anonimizados/dobles, sin red, y
   demostrar fallo contra `fd6cc70`.
5. Ejecutar primero validaciones dirigidas de los cinco casos afectados; solo
   si no hay bloqueos reales, repetir una vez el smoke canónico.

No cambiar golden, `expected_facts`, presupuestos, umbrales, cardinalidades,
contratos públicos ni el criterio de suficiencia RF-211. No ejecutar `full`
antes de un smoke formal verde.
