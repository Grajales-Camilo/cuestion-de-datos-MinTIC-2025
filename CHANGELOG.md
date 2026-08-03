# Changelog

Los cambios relevantes del proyecto se documentan en este archivo.

## 2.0.0 — en preparación

### Añadido

- Backend FastAPI separado con agente determinista multi-paso.
- PostgreSQL con `pgvector` para catálogo, embeddings, corridas y evidencia.
- Integración real con Gemini y Socrata desde el backend.
- API REST/SSE `/v2` con acceso por token de corrida.
- Frontend v2 con consentimiento, historial, línea de tiempo, evidencia y documento por secciones.
- Persistencia local, importación DOCX y exportación Word con citas.
- Staging aislado accesible mediante `preview.cuestiondedatos.com`.
- Pruebas unitarias, E2E, accesibilidad y auditoría del bundle.

### Cambiado

- La rama de integración y rama predeterminada del repositorio pasa a ser `v2`.
- La recuperación deja la lista fija de cinco datasets y usa el catálogo indexado de datos.gov.co.
- El navegador deja de ejecutar la orquestación del agente y consume directamente el backend FastAPI.

### Eliminado

- Endpoint serverless legado `pages/api/consultar_v2.js`.
- Prompt y tabla DIVIPOLA hardcodeada usados únicamente por ese endpoint.
- Plantillas v1 sustituidas por el modelo documental versionado de v2.
- Dependencias visuales sin consumidores: `framer-motion` y `react-joyride`.

### Pendiente antes de producción

- Cumplir las puertas vigentes de T-617 y las autorizaciones independientes de T-701, T-702 y T-703.
- Promover el frontend y backend únicamente con la evidencia exigida por el paquete SDD.
