// pages/api/consultar_v2.js
import { SYSTEM_PROMPT } from "../../utils/systemPrompt";
import { consultarDivipola } from "../../utils/maestro_divipola";

export default async function handler(req, res) {
    if (req.method !== 'POST') return res.status(405).json({ error: 'Método no permitido' });

    const { pregunta } = req.body;
    const apiKey = process.env.GOOGLE_API_KEY;
    const socrataToken = process.env.SOCRATA_APP_TOKEN;

    if (!apiKey) return res.status(500).json({ error: 'Falta la API Key' });

    // --- FUNCIONES AUXILIARES ---
    async function llamarGemini(mensajes) {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                contents: mensajes,
                generationConfig: { responseMimeType: "application/json", temperature: 0.2 }
            })
        });
        const data = await response.json();
        if (!data.candidates?.[0]?.content?.parts?.[0]?.text) return null;

        try {
            return JSON.parse(data.candidates[0].content.parts[0].text);
        } catch (e) {
            console.error("JSON Inválido IA:", data.candidates[0].content.parts[0].text);
            return null;
        }
    }

    async function herramientaExplorar(datasetId, columna, busqueda) {
        console.log(`🕵️ EXPLORANDO SOCRATA: ${datasetId}.${columna} LIKE '%${busqueda}%'`);
        // Límite aumentado a 20 para ver más opciones
        const soql = `SELECT distinct ${columna} WHERE upper(${columna}) LIKE upper('%${busqueda}%') LIMIT 20`;
        const url = `https://www.datos.gov.co/resource/${datasetId}.json?$query=${encodeURIComponent(soql)}`;
        const headers = { 'Accept': 'application/json' };
        if (socrataToken) headers['X-App-Token'] = socrataToken;
        const resp = await fetch(url, { headers });
        if (!resp.ok) return ["Error consultando"];
        const datos = await resp.json();
        return datos.map(d => d[columna]);
    }

    try {
        // --- INICIO AGENTE ---
        let historialMensajes = [
            { role: "user", parts: [{ text: `${SYSTEM_PROMPT}\n\nPREGUNTA DEL USUARIO: "${pregunta}"` }] }
        ];

        console.log("🤖 Iniciando Gemini...");
        let respuestaIA = await llamarGemini(historialMensajes);

        let intentos = 0;
        const MAX_INTENTOS = 5;

        // --- BUCLE DE RAZONAMIENTO ---
        while (respuestaIA && (respuestaIA.tool_use) && intentos < MAX_INTENTOS) {
            intentos++;
            let contextoHallazgos = "";

            // CASO A: CONSULTAR DIVIPOLA
            if (respuestaIA.tool_use === "consultar_divipola") {
                const { termino } = respuestaIA;
                console.log(`🌍 BUSCANDO GEOGRAFÍA: '${termino}'`);
                const geoData = consultarDivipola(termino);

                if (geoData) {
                    // AQUÍ ESTÁ EL CAMBIO CLAVE: Le mostramos el campo 'busqueda_segura'
                    contextoHallazgos = `[SISTEMA]: Encontré la ubicación '${termino}':
                    - Código DIVIPOLA: "${geoData.codigo}"
                    - Nombre Oficial: "${geoData.municipio}"
                    - SQL Seguro (SALUD): "${geoData.busqueda_segura}" 
                    - Texto APC: "${geoData.busqueda_apc}"
                    
                    Para el dataset de SALUD, usa obligatoriamente: upper(municipio) LIKE '${geoData.busqueda_segura}'`;
                } else {
                    contextoHallazgos = `[SISTEMA]: No encontré '${termino}' en el maestro DIVIPOLA. Intenta buscar por el nombre del departamento o usa 'explorar_valores'.`;
                }
            }

            // CASO B: EXPLORAR VALORES SOCRATA
            else if (respuestaIA.tool_use === "explorar_valores") {
                const { dataset_id, columna, termino_busqueda } = respuestaIA;
                console.log(`🔍 BUSCANDO VALORES: '${termino_busqueda}' en ${columna}`);
                const hallazgos = await herramientaExplorar(dataset_id, columna, termino_busqueda);
                contextoHallazgos = `[SISTEMA]: Resultados reales en columna '${columna}': ${JSON.stringify(hallazgos)}.`;
            }

            // Inyectar feedback
            historialMensajes.push({ role: "model", parts: [{ text: JSON.stringify(respuestaIA) }] });
            historialMensajes.push({ role: "user", parts: [{ text: contextoHallazgos }] });

            // Consultar de nuevo
            console.log(`🧠 Pensando (Intento ${intentos})...`);
            respuestaIA = await llamarGemini(historialMensajes);
        }

        // --- EJECUCIÓN FINAL ---
        if (!respuestaIA || !respuestaIA.queries) {
            return res.status(200).json({
                intention: "Error",
                explanation: "No pude concretar la consulta tras investigar.",
                resultados: []
            });
        }

        const socrataHeaders = { 'Accept': 'application/json' };
        if (socrataToken) socrataHeaders['X-App-Token'] = socrataToken;

        const resultadosReales = await Promise.all(
            respuestaIA.queries.map(async (q) => {
                try {
                    const cleanSoql = q.soql.replace(/;$/, '').trim();
                    const socrataUrl = `https://www.datos.gov.co/resource/${q.dataset_id}.json?$query=${encodeURIComponent(cleanSoql)}`;
                    console.log(`🌐 QUERY FINAL: ${cleanSoql}`);

                    const responseSocrata = await fetch(socrataUrl, { method: 'GET', headers: socrataHeaders });

                    // --- NUEVA VALIDACIÓN DE ERRORES ---
                    if (!responseSocrata.ok) {
                        const errorText = await responseSocrata.text();
                        console.error(`❌ ERROR SOCRATA (${responseSocrata.status}):`, errorText);
                        throw new Error(`Socrata falló: ${responseSocrata.status} - ${errorText}`);
                    }
                    // ------------------------------------

                    const dataReal = await responseSocrata.json();
                    return { dataset_id: q.dataset_id, query: cleanSoql, datos: dataReal };
                } catch (error) {
                    console.error("💥 Excepción en consulta:", error.message);
                    return { dataset_id: q.dataset_id, error: error.message, datos: [] };
                }
            })
        );

        return res.status(200).json({ ...respuestaIA, resultados: resultadosReales });

    } catch (error) {
        console.error("Server Error:", error);
        return res.status(500).json({ error: error.message });
    }
}