import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function HelpStep({ onPrev }) {
    const faqs = [
        {
            question: "¿Qué es la arquitectura ActRAG?",
            answer: "ActRAG (Active Retrieval-Augmented Generation) es una evolución de los sistemas RAG tradicionales. En lugar de solo buscar información pasivamente, nuestros agentes 'exploran' activamente las bases de datos, formulando múltiples consultas SQL y cruzando fuentes para encontrar evidencia precisa."
        },
        {
            question: "¿Cómo se garantizan los datos?",
            answer: "La plataforma se conecta directamente a la API SODA (Socrata Open Data API) del gobierno colombiano. Los datos no son almacenados por nosotros, sino consultados en tiempo real desde la fuente oficial (www.datos.gov.co), garantizando transparencia y actualización."
        },
        {
            question: "¿Qué hago si no encuentro datos de mi municipio?",
            answer: "El sistema intenta inferir códigos DIVIPOLA. Si un municipio pequeño no tiene datos específicos en un dataset nacional, el agente buscará datos departamentales o promedios regionales para ofrecerte un contexto útil."
        },
        {
            question: "¿Necesito descargar los datasets?",
            answer: "No. Nuestra plataforma consulta los datos directamente en la nube a través de las APIs de datos abiertos. Esto garantiza que siempre estés trabajando con la versión más reciente de la información sin ocupar espacio en tu dispositivo."
        },
        {
            question: "¿El servicio es gratuito?",
            answer: "Sí, el uso de nuestra plataforma y el acceso a los datos abiertos es gratuito. Sin embargo, el procesamiento de inteligencia artificial utiliza la API de Google Gemini, la cual, aunque ofrece una capa gratuita generosa, puede generar costos por uso intensivo (tokens) si se supera el límite gratuito."
        },
        {
            question: "¿Mis API Keys están seguras?",
            answer: "Sí. En esta versión demo usamos llaves públicas limitadas. En una implementación real, las llaves se almacenan en variables de entorno en el servidor y nunca se exponen al cliente."
        }
    ];

    const [openIndex, setOpenIndex] = useState(null);

    return (
        <div className="flex flex-col lg:flex-row gap-8 max-w-7xl mx-auto h-full overflow-hidden">

            {/* Left Column: Architecture Image */}
            <motion.div
                initial={{ opacity: 0, x: -50 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex-1 flex flex-col justify-center"
            >
                <h2 className="text-3xl font-extrabold text-white mb-6">Arquitectura del Sistema</h2>
                <div className="relative group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000"></div>
                    <div className="relative bg-slate-900 ring-1 ring-slate-700/50 rounded-2xl overflow-hidden shadow-2xl">
                        <img
                            src="/images/cuestiondedatos.jpg"
                            alt="Diagrama de Arquitectura Cuestión de Datos"
                            className="w-full h-auto object-contain hover:scale-105 transition-transform duration-700"
                        />
                    </div>
                </div>
                <p className="text-slate-400 text-sm mt-4 text-center italic">
                    Flujo de datos desde la consulta del usuario hasta la generación de evidencia.
                </p>
            </motion.div>

            {/* Right Column: FAQ */}
            <motion.div
                initial={{ opacity: 0, x: 50 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 }}
                className="flex-1 flex flex-col h-full overflow-y-auto custom-scrollbar pr-2"
            >
                <h2 className="text-3xl font-extrabold text-white mb-6">Preguntas Frecuentes</h2>
                <div className="space-y-4">
                    {faqs.map((faq, index) => (
                        <div key={index} className="border border-slate-700 rounded-xl bg-slate-800/30 overflow-hidden">
                            <button
                                onClick={() => setOpenIndex(openIndex === index ? null : index)}
                                className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-800/50 transition-colors"
                            >
                                <span className="font-bold text-slate-200">{faq.question}</span>
                                <svg
                                    className={`w-5 h-5 text-cyan-500 transform transition-transform ${openIndex === index ? 'rotate-180' : ''}`}
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                                </svg>
                            </button>
                            <AnimatePresence>
                                {openIndex === index && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: 'auto', opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        className="overflow-hidden"
                                    >
                                        <div className="p-4 pt-0 text-slate-400 text-sm leading-relaxed border-t border-slate-700/50">
                                            {faq.answer}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    ))}
                </div>

                <div className="mt-8 p-4 bg-slate-800/50 rounded-xl border border-slate-700 flex items-center gap-4">
                    <div className="p-3 bg-slate-900 rounded-full border border-slate-600">
                        <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                        </svg>
                    </div>
                    <div>
                        <h4 className="text-sm font-bold text-white">Código Abierto (Open Source)</h4>
                        <p className="text-xs text-slate-400">
                            Este proyecto se distribuye bajo licencia <span className="text-yellow-400 font-mono">MIT</span>.
                            <br />
                            <a
                                href="https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2025"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-cyan-400 hover:text-cyan-300 hover:underline inline-flex items-center gap-1 mt-1"
                            >
                                Ver repositorio en GitHub
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                            </a>
                        </p>
                    </div>
                </div>

                <div className="mt-auto pt-4 flex justify-end">
                    <button
                        onClick={onPrev}
                        className="px-6 py-3 text-slate-400 hover:text-white font-medium transition-colors flex items-center gap-2"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                        Volver al Lienzo
                    </button>
                </div>
            </motion.div>
        </div>
    );
}
