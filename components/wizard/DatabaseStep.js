import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const USED_DATASETS_IDS = [
    "2d3i-f9wd", // APC
    "feim-cysj", // Senado
    "thui-g47e", // Salud
    "2v94-3ypi", // Educación
];

const SISBEN_KEYWORDS = ["sisbén", "sisben"];

export default function DatabaseStep({ onNext, onPrev }) {
    const [datasets, setDatasets] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchDatasets = async () => {
            try {
                // El dataset v8aw-jabd fue descontinuado, se reemplaza por el actualizado de la Hoja de Ruta Nacional 2025: fn2v-r4gu
                const res = await fetch('https://www.datos.gov.co/resource/fn2v-r4gu.json?$limit=1000', {
                    headers: {
                        'X-App-Token': '10zQS6qOBoGXQeOSYQ7KfeSAZ'
                    }
                });
                let data = await res.json();

                // Si la API no contesta un arreglo (ej. error de socrata), se pasa un arreglo vacío para prevenir "n.map is not a function"
                if (!Array.isArray(data)) {
                    console.error("Error devuelto por la API:", data);
                    data = [];
                }

                setDatasets(data);
            } catch (error) {
                console.error("Error fetching datasets list:", error);
                setDatasets([]);
            } finally {
                setLoading(false);
            }
        };

        fetchDatasets();
    }, []);

    const isUsedDataset = (ds) => {
        // Check by ID in the URL or content if available, or strict match on known IDs
        const link = ds.enlace_portal_de_datos || ds.enlace_portal_dato_abierto || "";
        const idMatch = USED_DATASETS_IDS.some(id => link.includes(id));

        // Check for Sisbén specifically by name since the URL might not contain the ID
        const nameMatch = SISBEN_KEYWORDS.some(keyword =>
            (ds.conjunto_de_datos || ds.conjunto_datos_priorizados || "").toLowerCase().includes(keyword) &&
            (ds.conjunto_de_datos || ds.conjunto_datos_priorizados || "").toLowerCase().includes("beneficiarios")
        );

        return idMatch || nameMatch;
    };

    return (
        <div className="max-w-6xl mx-auto space-y-8 h-full flex flex-col">
            <div className="text-center space-y-4 flex-shrink-0">
                <h2 className="text-4xl font-extrabold text-white">Fuentes de Datos Estratégicas</h2>
                <div className="max-w-3xl mx-auto space-y-2">
                    <p className="text-lg text-slate-400">
                        Conexión con las bases de datos estratégicas de la <a href="https://www.datos.gov.co/stories/s/1-Hoja-de-Ruta-Nacional-de-Datos-Abiertos-2025/ivxt-5jyc/" target="_blank" rel="noopener noreferrer" className="text-cyan-400 font-semibold hover:underline">Hoja de Ruta Nacional 2025-2026</a>.
                    </p>
                    <div className="space-y-1 pt-2">
                        <p className="text-sm text-slate-500 italic">
                            * El estado <span className="text-[#39ff14] font-bold">ONLINE</span> indica que el conjunto de datos está marcado como "SI" en la política de datos abiertos de la entidad.
                        </p>
                        <p className="text-sm text-slate-400">
                            ✅ Las bases de datos marcadas como "Usando" son las que estamos utilizando en este despliegue. Más adelante podrá anexar otras bases de datos que necesite.
                        </p>
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center py-20">
                    <div className="w-16 h-16 border-4 border-blue-500/30 border-t-cyan-400 rounded-full animate-spin"></div>
                </div>
            ) : (
                <div className="bg-slate-900/50 rounded-2xl border border-slate-800 overflow-hidden flex-grow flex flex-col min-h-0">
                    <div className="overflow-y-auto custom-scrollbar p-0">
                        <table className="w-full text-left border-collapse">
                            <thead className="bg-slate-900/80 sticky top-0 z-10 backdrop-blur-sm">
                                <tr>
                                    <th className="p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-800 text-center w-20">Usando</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-800">Dataset</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-800">Entidad</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-800">Categoría</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-800 text-right">Estado</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/50">
                                {datasets.map((ds, i) => {
                                    const isOnline = ds.dato_abierto === 'SI';
                                    const used = isUsedDataset(ds);

                                    const datasetName = ds.conjunto_de_datos || ds.conjunto_datos_priorizados || "Sin Nombre";
                                    const datasetDesc = ds.descripci_n || ds.descripcion;
                                    const datasetEntity = ds.nombre_entidades_responsables || ds.entidades_responsables || "N/A";
                                    const datasetCategory = ds.categor_a || ds.categoria || "General";

                                    return (
                                        <motion.tr
                                            key={ds[':id'] || ds.id || i}
                                            initial={{ opacity: 0, y: 10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: i * 0.02 }}
                                            className={`group transition-colors ${used ? 'bg-cyan-900/10 hover:bg-cyan-900/20' : 'hover:bg-slate-800/40'}`}
                                        >
                                            <td className="p-4 text-center">
                                                {used && <span className="text-lg">✅</span>}
                                            </td>
                                            <td className="p-4">
                                                <div className={`font-semibold transition-colors ${used ? 'text-cyan-300' : 'text-slate-200 group-hover:text-cyan-400'}`}>
                                                    {datasetName}
                                                </div>
                                                {datasetDesc && (
                                                    <div className="text-xs text-slate-500 mt-1 line-clamp-1 max-w-md">
                                                        {datasetDesc}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="p-4 text-sm text-slate-400">
                                                {datasetEntity}
                                            </td>
                                            <td className="p-4">
                                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-900/30 text-blue-400 border border-blue-800/50">
                                                    {datasetCategory}
                                                </span>
                                            </td>
                                            <td className="p-4 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-[#39ff14] shadow-[0_0_8px_rgba(57,255,20,0.6)]' : 'bg-slate-600'}`}></span>
                                                    <span className={`text-xs font-mono ${isOnline ? 'text-[#39ff14]' : 'text-slate-500'}`}>
                                                        {isOnline ? 'ONLINE' : 'OFFLINE'}
                                                    </span>
                                                </div>
                                            </td>
                                        </motion.tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <div className="flex justify-center gap-6 pt-4 flex-shrink-0">
                <button
                    onClick={onPrev}
                    className="px-8 py-3 text-slate-400 hover:text-white font-medium transition-colors"
                >
                    Atrás
                </button>
                <motion.button
                    whileHover={{ scale: 1.05, boxShadow: "0 0 25px rgba(6, 182, 212, 0.4)" }}
                    whileTap={{ scale: 0.95 }}
                    onClick={onNext}
                    className="px-10 py-4 bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-xl font-bold rounded-2xl shadow-xl transition-all flex items-center gap-3"
                >
                    Ingresar al Lienzo de Trabajo
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                </motion.button>
            </div>
        </div>
    );
}
