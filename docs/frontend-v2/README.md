# Documentación del Frontend v2

## Propósito

Esta carpeta reúne la planificación ejecutable y las fuentes de consulta del
Frontend v2 de Cuestión de Datos. Su objetivo es permitir que sesiones y
agentes distintos continúen el desarrollo por fases sin depender de la memoria
de una conversación anterior.

Los documentos de esta carpeta son no normativos. Sirven para ejecutar y
explicar el trabajo, pero se subordinan al paquete SDD del proyecto.

## Jerarquía documental

La autoridad se aplica en este orden:

1. `specs/constitution.md`
2. `specs/001-cuestion-de-datos-v2/spec.md`
3. `specs/001-cuestion-de-datos-v2/research.md`
4. `specs/001-cuestion-de-datos-v2/plan.md`
5. `specs/001-cuestion-de-datos-v2/contracts/`
6. `specs/001-cuestion-de-datos-v2/data-model.md`
7. `specs/001-cuestion-de-datos-v2/pruebas.md`
8. `specs/001-cuestion-de-datos-v2/tasks.md`
9. `specs/001-cuestion-de-datos-v2/quickstart.md`
10. `docs/frontend-v2/implementation-plan.md`
11. `docs/frontend-v2/architecture-principles.md`
12. Impeccable y otras herramientas de apoyo
13. Código

`AGENTS.md` de la raíz y `frontend/AGENTS.md` son instrucciones operativas:
obligan al agente a respetar esta jerarquía, pero no la modifican.

Ante una contradicción:

1. No asumir ni resolverla silenciosamente.
2. Aplicar la fuente de mayor jerarquía.
3. Registrar el conflicto y su impacto.
4. Detener únicamente el trabajo dependiente de la contradicción.
5. No cambiar contratos o requisitos para acomodar el código sin autorización.

## Mapa de documentos

### [`implementation-plan.md`](./implementation-plan.md)

Plan técnico ejecutable y no normativo. Contiene:

- diagnóstico del frontend legacy y del runtime determinista;
- requisitos y brechas;
- arquitectura objetivo REST/SSE;
- estado, persistencia, componentes y Tiptap;
- seguridad, accesibilidad y pruebas;
- fases F0–F10 y criterios de aceptación;
- riesgos R-01…R-14;
- decisiones abiertas D-1…D-9;
- estrategia de Git y secuencia propuesta de incrementos.

No se debe leer solamente la sección de la fase: las secciones 1, 4, 14, 16,
17 y 18 establecen el contexto transversal que evita decisiones locales
incompatibles.

### [`architecture-principles.md`](./architecture-principles.md)

Fuente extensa con capítulos seleccionados de *Fundamentos de Arquitectura de
Software*. Es material de consulta, no una instrucción autónoma ni una fuente
normativa. Se lee selectivamente según la fase:

| Capítulo | Aplicación en Cuestión de Datos |
|---|---|
| 3. Modularidad | Cohesión de `lib/`, fronteras con React, reducer y dependencias mínimas en F2–F7 |
| 6. Medición y gobernanza | Funciones de aptitud, CI, cobertura, accesibilidad y gates en F0 y F8 |
| 15. Arquitectura dirigida por eventos | SSE, asincronía, reconexión, orden, deduplicación y `Last-Event-ID` en F2 y F3 |
| 21. Decisiones arquitectónicas | ADR para D-1…D-9 y decisiones nuevas con trade-offs relevantes |
| 26. Intersecciones arquitectónicas | Frontera navegador React ↔ backend FastAPI determinista en F2–F7 |

No se debe extrapolar el capítulo 15 para introducir brokers, event sourcing o
microservicios. La arquitectura acordada es una solicitud REST seguida por un
stream SSE autenticado.

### [`frontend/README.md`](../../frontend/README.md)

Manual operativo del proyecto: stack comprobado, instalación, comandos,
variables, ejecución local y estructura objetivo. Debe actualizarse cuando una
fase cambie comandos o requisitos operativos.

### [`frontend/AGENTS.md`](../../frontend/AGENTS.md)

Reglas obligatorias y acotadas al frontend: lectura por fase, límites
arquitectónicos, disciplina de Git, pruebas, accesibilidad y cierre de sesión.

## Referencias de diseño incorporadas al plan

Los siguientes capítulos de *Diseño de interfaces para la web actual* se usan
como fundamentos de diseño. Sus decisiones aplicables deben quedar traducidas
a tokens, componentes, pruebas y criterios del plan; el agente no debe tratarlos
como autoridad superior a WCAG, la constitución o los requisitos.

| Capítulo | Fases | Aplicación práctica |
|---|---|---|
| 1. Diseñando por el principio | F1 | Guía de estilo, jerarquía, escala, personalidad, tokens y primitivas |
| 3. Conceptos básicos de CSS | F1, F8 | Reset, cascada, tipografía y contrastes verificables |
| 4. Colocación de componentes en CSS | F1 | Flexbox/Grid, responsive y reflujo sin scroll horizontal a 320 px |
| 6. Accesibilidad | F1, F8 | WCAG 2.2 AA, semántica, teclado, foco, lector de pantalla y evaluación manual |
| 7. Usabilidad en la web | F3, F8 | Visibilidad del estado, lenguaje claro y prevención/recuperación de errores |

Impeccable complementa estas referencias con contexto de producto, crítica y
auditoría. No reemplaza las pruebas manuales ni puede cambiar el alcance de una
fase.

## Ruta de lectura por fase

| Fase | Secciones del plan | Arquitectura | Diseño/Impeccable |
|---|---|---|---|
| F0 | §§12, 14/F0, 15, 18, 20 | Cap. 6 | Impeccable: instalación, inicialización y baseline |
| F1 | §§8, 11, 14/F1 | — | Caps. 1, 3, 4 y 6; Impeccable |
| F2 | §§4–6, 10, 12, 14/F2 | Caps. 3, 15 y 26 | Sin trabajo visual |
| F3 | §§5–8, 10–12, 14/F3 | Caps. 3, 15 y 26 | Cap. 7; Impeccable |
| F4 | §§4.7, 8.2, 8.3, 12, 14/F4 | Caps. 3, 21 y 26 | Impeccable para presentación de evidencia |
| F5 | §§8, 9, 11, 12, 14/F5 | Caps. 3, 21 y 26 | Caps. 1 y 6; Impeccable |
| F6 | §§7, 9.2, 12, 14/F6 | Caps. 3, 6, 21 y 26 | Revisión de salida DOCX |
| F7 | §§8, 9.1, 10, 12, 14/F7 | Caps. 3, 21 y 26 | Caps. 6 y 7; Impeccable |
| F8 | §§10–12, 14/F8 | Cap. 6 | Caps. 3, 6 y 7; Impeccable |
| F9 | §§2.4, 15, 14/F9 | Caps. 6, 21 y 26 | Auditoría final de regresión |
| F10 | §§4.3, 12, 14/F10 | Caps. 3, 21 y 26 | Solo si el alcance opcional se autoriza |

Para localizar un capítulo en la referencia extensa, buscar su encabezado
`Capítulo N` en lugar de recorrer el archivo completo.

## Cómo determinar el punto de continuación

No existe un “estado de fase” confiable solo porque aparezca en un prompt o en
un resumen anterior. Cada sesión debe reconstruirlo con evidencia:

1. Identificar la tarea vigente en `tasks.md` y los requisitos asociados.
2. Revisar la fase y los criterios de aceptación del plan.
3. Inspeccionar rama, commit, `git status`, diff y archivos existentes.
4. Ejecutar o revisar las pruebas y reportes que demuestran el último gate.
5. Clasificar cada criterio como `PASS`, `FAIL` o `NO VERIFICADO`.
6. Continuar desde el primer criterio que no esté demostrado.

La recomendación inicial del plan es cerrar F0 y después implementar como
primer incremento de F2 el parser SSE puro con ocho pruebas. Esto es el orden
por defecto, no una afirmación de que esas fases sigan pendientes: la sesión
debe verificarlo.

Una fase no se cierra con mocks o pruebas parciales si su aceptación exige un
backend real, accesibilidad manual, CI o evidencia de runtime.

## Protocolo de inicio de sesión

Toda sesión de desarrollo debe declarar antes de modificar archivos:

- fase e incremento;
- requisitos `RF-###`, `RNF-###` y tarea aplicable;
- criterios de aceptación que intentará cerrar;
- contratos y decisiones relevantes;
- archivos previstos;
- pruebas previstas;
- exclusiones explícitas;
- estado del worktree y cambios preexistentes.

El descubrimiento de código comienza con `codebase-memory-mcp`; la verificación
final se hace contra los archivos y el runtime reales.

## Protocolo de cierre y entrega entre sesiones

El reporte final debe permitir continuar sin depender de la conversación que
termina. Debe incluir:

1. Fase e incremento trabajado.
2. Requisitos y criterios cubiertos.
3. Resultado `PASS`/`FAIL`/`NO VERIFICADO` por criterio.
4. Archivos propios creados o modificados.
5. Comandos ejecutados y resultados medidos.
6. Evidencia real usada: fixtures, run IDs, commits, reportes o capturas.
7. Decisiones tomadas y ADR asociado, si aplica.
8. Riesgos, fallos y bloqueos pendientes.
9. Confirmación de que se preservaron cambios ajenos.
10. Un único siguiente incremento concreto y su gate de entrada.

No se avanza automáticamente al siguiente incremento. No se marca `tasks.md`
ni se declara una fase terminada sin cumplir todos los criterios pertinentes.

## Registros de Decisiones Arquitectónicas

Las decisiones D-1…D-9 y cualquier decisión nueva que cambie fronteras,
dependencias, seguridad, persistencia o contratos deben registrarse, una vez
autorizadas, bajo:

```text
docs/frontend-v2/adr/
```

Convención sugerida:

```text
ADR-0001-titulo-breve.md
```

Cada ADR debe contener:

1. Título.
2. Estado: `Propuesto`, `Aceptado` o `Reemplazado`.
3. Contexto y fuerzas en tensión.
4. Decisión.
5. Consecuencias positivas y negativas.
6. Alternativas consideradas.
7. Requisitos, contratos y fases afectados.
8. Evidencia y fecha de aprobación humana.
9. ADR reemplazado o sucesor, cuando aplique.

Un ADR propuesto no autoriza una implementación. Las decisiones marcadas como
`PENDIENTE` en `research.md` mantienen su poder de bloqueo aunque exista un ADR
local.

## Mantenimiento documental

- Evitar duplicar el plan en `frontend/README.md` o en este índice.
- Si cambia la jerarquía o el enrutamiento por fases, actualizar juntos este
  archivo, `frontend/AGENTS.md` y, si corresponde, `AGENTS.md` de la raíz.
- Si cambian comandos, variables o estructura operativa, actualizar
  `frontend/README.md` en el mismo incremento.
- Si cambia un requisito, contrato o tarea, hacerlo en el documento normativo
  correspondiente con autorización; no corregirlo solo aquí.
- Conservar los documentos de referencia como fuentes consultivas y evitar que
  sus recomendaciones genéricas sustituyan decisiones específicas del
  proyecto.
