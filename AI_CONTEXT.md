# Contexto del Proyecto: Cuestión de Datos

Este documento resume la arquitectura, tecnologías y propósito del proyecto para proporcionar contexto rápido a modelos de Inteligencia Artificial.

## 1. Identidad del Proyecto
*   **Nombre:** Cuestión de Datos
*   **Propósito:** Plataforma web que integra periodismo de datos, ciencia política y analítica para apoyar la toma de decisiones en política pública en Colombia.
*   **Objetivo:** Democratizar el acceso a datos y modelos matemáticos para el diseño y monitoreo de intervenciones sociales.

## 2. Stack Tecnológico
*   **Core:** Next.js 14 (Pages Router), React 18.
*   **Lenguajes:** JavaScript (ES6+), HTML5, CSS3.
*   **Estilos:** Tailwind CSS (Utility-first), Framer Motion (Animaciones).
*   **Visualización de Datos:**
    *   D3.js (Gráficos personalizados y modelos matemáticos).
    *   Chart.js / React-Chartjs-2 (Gráficos estadísticos estándar).
    *   React-Globe.gl / Three.js (Visualización geoespacial 3D).
*   **Matemáticas:** KaTeX / React-KaTeX (Renderizado de fórmulas).
*   **Datos:** PapaParse (Parsing de CSV en frontend).

## 3. Estructura de Directorios Clave
*   `/pages`: Rutas de la aplicación (Next.js Pages Router).
*   `/components`: Componentes de React reutilizables.
    *   `/civitas`: Componentes específicos del laboratorio político.
    *   `/matematicas-politica`: Componentes del libro interactivo.
*   `/public/data`: Almacenamiento de datos estáticos (CSV, JSON, GeoJSON).
*   `/data`: Lógica y contenido estático estructurado (ej. capítulos del libro).
*   `/styles`: Archivos CSS globales.

## 4. Módulos Principales
### A. Home / Newsroom
*   **Ruta:** `/`
*   **Función:** Portada tipo "diario" con noticias destacadas y resumen de sentimiento social.
*   **Componentes Clave:** `FeaturedNews`, `SentimentSummary`.

### B. CIVITAS (Laboratorio Político)
*   **Ruta:** `/civitas`
*   **Función:** Dashboard para análisis electoral y de opinión pública.
*   **Características:** Modelos de predicción, análisis de encuestas, "Brain Voter" (conductual).

### C. Recursos
*   **Ruta:** `/recursos`
*   **Sub-secciones:**
    *   **Datos Abiertos:** Catálogo de datasets (`/recursos/datos-abiertos`).
    *   **Matemáticas en Política:** Libro interactivo con modelos de teoría de juegos (`/recursos/matematicas-politica`).
    *   **Guías y Herramientas:** Tutoriales y visualizaciones reutilizables.

### D. República Digital
*   **Ruta:** `/republica-digital`
*   **Función:** Espacio para gobernanza digital y participación ciudadana.

## 5. Flujo de Datos
*   La aplicación prioriza la carga de datos estáticos desde `/public/data` para facilitar el despliegue y la replicabilidad sin backend complejo inicial.
*   Los componentes de visualización consumen estos datos (CSV/JSON) y los renderizan en el cliente.
