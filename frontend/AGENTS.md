# Instrucciones para agentes — Frontend v2

## Alcance

Estas instrucciones se aplican a cualquier trabajo dentro de `frontend/` y
complementan el `AGENTS.md` de la raíz. No sustituyen la constitución, la
especificación, los contratos ni `tasks.md`.

El frontend v2 se desarrolla de forma incremental sobre el proyecto Next.js
existente. El runtime determinista de FastAPI es el único modelo funcional y
de aceptación. El frontend legacy puede consultarse para inventario y
orientación, pero no debe convertirse en fallback funcional ni justificar una
implementación incompatible con el núcleo determinista.

## Lectura obligatoria

Antes de escribir código, el agente debe haber completado el orden general de
lectura de `AGENTS.md` en la raíz. Después debe leer, en este orden:

1. `docs/frontend-v2/README.md`, para ubicar la fase y las fuentes aplicables.
2. `frontend/README.md`, para conocer el estado operativo comprobado y los
   comandos realmente disponibles.
3. `docs/frontend-v2/implementation-plan.md`:
   - siempre: §§1, 4, 14, 16, 17 y 18;
   - además: la sección de la fase activa, sus pruebas y sus riesgos.
4. Solo los capítulos aplicables de
   `docs/frontend-v2/architecture-principles.md`, usando la tabla de
   enrutamiento del índice documental. No es necesario leer ese archivo entero
   en cada sesión.
5. La skill Impeccable, si la tarea modifica UI, estilos, interacción,
   responsive o accesibilidad. Si está instalada, se debe leer completamente
   `.agents/skills/impeccable/SKILL.md` antes de usarla.

Si el usuario identifica una fase o incremento concreto, ese alcance manda.
Si no lo hace, el agente debe comprobar `tasks.md`, el plan de implementación,
Git y las pruebas antes de inferir cuál es el siguiente incremento. Una casilla
marcada o una afirmación de una sesión anterior no reemplaza la evidencia del
worktree.

## Enrutamiento por fase

| Fase | Consulta principal | Referencias seleccionadas |
|---|---|---|
| F0 | Plan §§12, 14/F0, 15, 18 y 20 | Arquitectura, cap. 6: funciones de aptitud y gobernanza |
| F1 | Plan §§8, 11 y 14/F1 | Diseño, caps. 1, 3, 4 y 6; Impeccable |
| F2 | Plan §§4–6, 10, 12 y 14/F2 | Arquitectura, caps. 3, 15 y 26 |
| F3 | Plan §§5–8, 10–12 y 14/F3 | Arquitectura, caps. 3, 15 y 26; diseño, cap. 7; Impeccable |
| F4 | Plan §§4.7, 8.2, 8.3, 12 y 14/F4 | Arquitectura, caps. 3, 21 y 26; Impeccable para la presentación |
| F5 | Plan §§8, 9, 11, 12 y 14/F5 | Arquitectura, caps. 3, 21 y 26; diseño, caps. 1 y 6; Impeccable |
| F6 | Plan §§7, 9.2, 12 y 14/F6 | Arquitectura, caps. 3, 6, 21 y 26 |
| F7 | Plan §§8, 9.1, 10, 12 y 14/F7 | Arquitectura, caps. 3, 21 y 26; diseño, caps. 6 y 7; Impeccable |
| F8 | Plan §§10–12 y 14/F8 | Arquitectura, cap. 6; diseño, caps. 3, 6 y 7; Impeccable |
| F9 | Plan §§2.4, 15 y 14/F9 | Arquitectura, caps. 6, 21 y 26 |
| F10 | Plan §§4.3 y 14/F10 | Arquitectura, caps. 3, 21 y 26 |

Cualquier decisión D-1…D-9 requiere además el capítulo 21 y el procedimiento
de ADR descrito en `docs/frontend-v2/README.md`.

## Reglas arquitectónicas obligatorias

- Mantener el navegador como consumidor y presentador: no inventar, completar
  ni recalcular hechos que el backend no afirmó.
- Mantener separados claims, evidencia tabular, hechos textuales, advertencias
  de presentación y aportes manuales.
- Consumir el backend determinista directamente mediante
  `NEXT_PUBLIC_BACKEND_URL`. No crear un proxy de Next ni recurrir al endpoint
  legacy para simular compatibilidad.
- Para SSE usar `fetch`, lectura incremental y encabezado `Authorization`.
  `EventSource` no es válido porque no permite el encabezado requerido.
- Nunca incluir el token de corrida en URL, logs, mensajes de error, telemetría
  o estado serializable del reducer. Su almacenamiento debe seguir la decisión
  D-1 una vez aceptada; no elegir implícitamente entre `sessionStorage` y
  `localStorage`.
- Tratar el flujo como una combinación de solicitud REST y eventos SSE, no
  como autorización para introducir brokers, event sourcing o microservicios.
- Separar responsabilidades: decodificación UTF-8, parsing SSE, transporte,
  deduplicación, reconciliación, reducer y presentación son módulos distintos.
- Mantener `lib/` libre de React siempre que el plan defina lógica pura.
- El reducer debe ser puro, exhaustivo e idempotente. Un `seq` ya observado es
  un no-op; los comentarios/heartbeats no deben saturar el estado de UI.
- Ser tolerante a campos aditivos desconocidos y estricto con invariantes de
  seguridad, orden, estados terminales y contratos consumidos.
- No introducir Redux, Zustand, MSW, Storybook u otra dependencia fuera del
  plan sin una decisión documentada y autorización.

## Reglas de UI, UX y accesibilidad

- La interfaz y los mensajes de usuario deben estar en español claro. Los
  enums y detalles técnicos solo pueden aparecer en un disclosure técnico.
- WCAG 2.2 AA, navegación completa por teclado, foco visible, HTML semántico,
  nombres accesibles y reflujo sin scroll horizontal a 320 px son criterios de
  aceptación, no mejoras opcionales.
- El contenido dinámico usa una región `aria-live="polite"` agrupada; no se
  anuncia cada paso de forma agresiva.
- No usar `dangerouslySetInnerHTML`. El contenido del backend se presenta como
  texto y toda URL externa se valida antes de crear un enlace.
- Los tokens visuales del documento normativo y del plan prevalecen sobre
  preferencias genéricas, libros o sugerencias de Impeccable.
- Las herramientas automáticas de accesibilidad no sustituyen las pruebas
  manuales con teclado y lector de pantalla exigidas por el plan.
- Impeccable guía y audita; no puede alterar requisitos, contratos ni
  introducir rediseños fuera de la fase activa.

## Flujo obligatorio de cada sesión

### Al comenzar

1. Identificar fase, incremento, requisitos `RF-###`/`RNF-###` y criterios de
   aceptación.
2. Consultar primero `codebase-memory-mcp` para descubrir símbolos, rutas,
   dependencias y pruebas; contrastar después con los archivos reales.
3. Registrar rama, commit, `git status --short`, cambios preexistentes y
   comandos disponibles en `package.json`.
4. Confirmar que ninguna decisión `PENDIENTE` o D-1…D-9 bloquea el alcance.
5. Declarar qué archivos se espera tocar y qué queda expresamente fuera.

### Durante el trabajo

- Implementar un incremento pequeño y revisable.
- Preservar cambios ajenos y usar rutas explícitas; nunca `git add -A`.
- No modificar contratos, golden data, backend, migraciones o documentos
  normativos para acomodar el frontend sin autorización.
- Capturar fixtures únicamente de corridas reales y documentar procedencia,
  commit y anonimización. Nunca incluir tokens ni datos personales.
- Ejecutar las pruebas relacionadas después de cada cambio significativo.

### Al cerrar

1. Comparar el resultado con cada criterio de aceptación de la fase.
2. Ejecutar lint, pruebas, build y verificaciones E2E disponibles en esa fase.
3. Informar resultados reales, incluidos fallos, advertencias y pruebas no
   ejecutadas.
4. Mostrar los archivos propios modificados y comprobar que no se tocaron
   cambios preexistentes.
5. No marcar tareas ni fases como terminadas sin evidencia completa.
6. Dejar un único siguiente incremento concreto. No avanzar automáticamente a
   la fase siguiente ni crear commits, push o PR sin autorización.

## Decisiones y documentación

- `tasks.md` continúa siendo el backlog canónico.
- `docs/frontend-v2/implementation-plan.md` describe la ejecución, pero es no
  normativo.
- Las decisiones abiertas D-1…D-9 no se resuelven en código. Cuando el humano
  acepte una decisión, debe registrarse mediante un ADR según el índice
  documental.
- Si cambia una interfaz pública, primero debe autorizarse y actualizarse el
  contrato correspondiente. El frontend se adapta al contrato, no al revés.
- Al cambiar comandos, variables, estructura o estado operativo, actualizar
  `frontend/README.md` en el mismo incremento.
