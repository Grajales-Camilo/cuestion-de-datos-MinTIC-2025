// utils/maestro_divipola.js

const DATA_DIVIPOLA = [
    // --- CAPITALES ---
    {
        codigo: "11001",
        municipio: "BOGOTÁ",
        departamento: "BOGOTA D.C.",
        busqueda_apc: "Bogotá",
        busqueda_segura: "%BOGOT_%" // El _ sirve de comodín para A o Á
    },
    {
        codigo: "05001",
        municipio: "MEDELLÍN",
        departamento: "ANTIOQUIA",
        busqueda_apc: "Medellín",
        busqueda_segura: "%MEDELL_N%" // El _ sirve de comodín para I o Í
    },
    {
        codigo: "76001",
        municipio: "CALI",
        departamento: "VALLE DEL CAUCA",
        busqueda_apc: "Cali",
        busqueda_segura: "%CALI%"
    },
    {
        codigo: "08001",
        municipio: "BARRANQUILLA",
        departamento: "ATLANTICO",
        busqueda_apc: "Barranquilla",
        busqueda_segura: "%BARRANQUILLA%"
    },
    {
        codigo: "13001",
        municipio: "CARTAGENA",
        departamento: "BOLIVAR",
        busqueda_apc: "Cartagena",
        busqueda_segura: "%CARTAGENA%"
    },
    {
        codigo: "68001",
        municipio: "BUCARAMANGA",
        departamento: "SANTANDER",
        busqueda_apc: "Bucaramanga",
        busqueda_segura: "%BUCARAMANGA%"
    },
    {
        codigo: "54001",
        municipio: "CUCUTA",
        departamento: "NORTE DE SANTANDER",
        busqueda_apc: "Cúcuta",
        busqueda_segura: "%C_CUTA%"
    },
    {
        codigo: "17001",
        municipio: "MANIZALES",
        departamento: "CALDAS",
        busqueda_apc: "Manizales",
        busqueda_segura: "%MANIZALES%"
    },
    {
        codigo: "66001",
        municipio: "PEREIRA",
        departamento: "RISARALDA",
        busqueda_apc: "Pereira",
        busqueda_segura: "%PEREIRA%"
    },
    {
        codigo: "27001",
        municipio: "QUIBDÓ",
        departamento: "CHOCO",
        busqueda_apc: "Quibdó",
        busqueda_segura: "%QUIBD_%"
    },

    // --- DEPARTAMENTOS ---
    {
        codigo: "05",
        municipio: "TODO EL DEPARTAMENTO",
        departamento: "ANTIOQUIA",
        busqueda_apc: "Antioquia",
        busqueda_segura: "%ANTIOQUIA%"
    },
    {
        codigo: "11",
        municipio: "TODO EL DEPARTAMENTO",
        departamento: "BOGOTA D.C.",
        busqueda_apc: "Bogotá",
        busqueda_segura: "%BOGOT_%"
    },
    {
        codigo: "25",
        municipio: "TODO EL DEPARTAMENTO",
        departamento: "CUNDINAMARCA",
        busqueda_apc: "Cundinamarca",
        busqueda_segura: "%CUNDINAMARCA%"
    },
    {
        codigo: "76",
        municipio: "TODO EL DEPARTAMENTO",
        departamento: "VALLE DEL CAUCA",
        busqueda_apc: "Valle del Cauca",
        busqueda_segura: "%VALLE%"
    },
    {
        codigo: "27",
        municipio: "TODO EL DEPARTAMENTO",
        departamento: "CHOCO",
        busqueda_apc: "Chocó",
        busqueda_segura: "%CHOC_%"
    }
];

function normalizar(texto) {
    if (!texto) return "";
    return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

export function consultarDivipola(termino) {
    const termLimpio = normalizar(termino);

    // 1. Búsqueda exacta
    const exacto = DATA_DIVIPOLA.find(d =>
        normalizar(d.municipio) === termLimpio ||
        normalizar(d.departamento) === termLimpio
    );
    if (exacto) return exacto;

    // 2. Búsqueda parcial (contiene)
    return DATA_DIVIPOLA.find(d =>
        normalizar(d.municipio).includes(termLimpio) ||
        normalizar(d.departamento).includes(termLimpio)
    ) || null;
}