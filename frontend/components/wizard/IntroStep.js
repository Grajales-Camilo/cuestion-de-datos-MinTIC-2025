import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function IntroStep({ onNext }) {
    const objectives = [
        {
            text: "Decisiones basadas en evidencia",
            icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
            description: "Priorizamos hechos y datos verificables sobre la intuición para formular políticas más efectivas."
        },
        {
            text: "Análisis de datos públicos",
            icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10",
            description: "Procesamos grandes volúmenes de información gubernamental abierta para encontrar patrones ocultos."
        },
        {
            text: "Información estratégica",
            icon: "M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z",
            description: "Transformamos datos duros y complejos en información clara que facilita la comprensión y la acción."
        },
        {
            text: "Ética en IA y Transparencia",
            icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
            description: "Garantizamos el uso responsable de la inteligencia artificial, con trazabilidad clara de las fuentes."
        },
    ];

    const [hoveredIndex, setHoveredIndex] = useState(null);

    return (
        <div className="flex flex-col lg:flex-row items-center justify-between gap-16 max-w-7xl mx-auto">
            {/* Text Content */}
            <motion.div
                initial={{ opacity: 0, x: -50 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.8 }}
                className="flex-1 space-y-10"
            >
                <div className="space-y-6">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-900/30 border border-blue-500/30 text-blue-300 rounded-full text-xs font-bold tracking-widest uppercase backdrop-blur-sm"
                    >
                        <span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></span>
                        Datos al Ecosistema 2025
                    </motion.div>

                    <h1 className="text-6xl font-extrabold text-white leading-tight tracking-tight">
                        Cuestión de <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-600 animate-gradient-x">
                            Datos
                        </span>
                    </h1>

                    <p className="text-xl text-slate-300 leading-relaxed font-light">
                        Cuestión de Datos usa los LLMs como apoyo a la gestión pública mediante el cambio de algoritmos pasivos a
                        <span className="font-semibold text-white"> Agentes Exploradores (ActRAG)</span> capaces de navegar autónomamente por las bases de datos del Estado (datos.gov.co) para encontrar la evidencia que necesita para la formulación de hipótesis y árboles de problemas para el diseño de políticas públicas. Para lograrlo el sistema usa:
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 relative">
                    {objectives.map((obj, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.4 + (i * 0.1) }}
                            className="relative flex items-start gap-3 p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-blue-500/30 transition-all group cursor-pointer"
                            onMouseEnter={() => setHoveredIndex(i)}
                            onMouseLeave={() => setHoveredIndex(null)}
                            onClick={() => setHoveredIndex(i === hoveredIndex ? null : i)}
                        >
                            <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400 group-hover:text-cyan-300 group-hover:bg-blue-500/20 transition-colors">
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={obj.icon} />
                                </svg>
                            </div>
                            <span className="text-sm text-slate-300 font-medium">{obj.text}</span>

                            <AnimatePresence>
                                {hoveredIndex === i && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                        exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                        className="absolute top-full left-0 z-20 mt-2 w-64 p-3 bg-slate-800 border border-slate-600 rounded-lg shadow-xl text-xs text-slate-300"
                                    >
                                        {obj.description}
                                        <div className="absolute -top-1 left-8 w-2 h-2 bg-slate-800 border-t border-l border-slate-600 transform rotate-45"></div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    ))}
                </div>

                <motion.button
                    whileHover={{ scale: 1.05, boxShadow: "0 0 20px rgba(59, 130, 246, 0.5)" }}
                    whileTap={{ scale: 0.95 }}
                    onClick={onNext}
                    className="px-10 py-5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-lg font-bold rounded-2xl shadow-xl shadow-blue-900/20 transition-all flex items-center gap-4 group"
                >
                    Siguiente
                    <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                </motion.button>
            </motion.div>

            {/* Image Content */}
            <motion.div
                initial={{ opacity: 0, scale: 0.9, rotate: 5 }}
                animate={{ opacity: 1, scale: 1, rotate: 0 }}
                transition={{ duration: 0.8, delay: 0.2 }}
                className="flex-1 relative hidden lg:block"
            >
                <div className="text-center mb-6">
                    <h3 className="text-white font-bold text-2xl drop-shadow-md tracking-tight">Modelo de generación de valor público</h3>
                </div>
                <div className="relative z-10 bg-white/5 backdrop-blur-xl p-2 rounded-3xl border border-white/10 shadow-2xl transform hover:scale-[1.02] transition-transform duration-500">
                    <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/10 to-purple-500/10 rounded-3xl"></div>
                    <div className="relative">
                        <img
                            src="/ciclo-politicas.png"
                            alt="Ciclo de Políticas Públicas"
                            className="w-full h-auto rounded-2xl relative z-10 opacity-90 hover:opacity-100 transition-opacity"
                        />
                    </div>
                    <div className="text-center mt-2 pb-2">
                        <p className="text-[10px] text-slate-400 uppercase tracking-widest">Fuente: Diplomado en políticas públicas. ESAP 2024</p>
                    </div>
                </div>

                {/* Decorative blobs */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[140%] h-[140%] bg-gradient-to-tr from-blue-600/20 to-purple-600/20 rounded-full blur-[100px] -z-10"></div>
            </motion.div>
        </div>
    );
}
