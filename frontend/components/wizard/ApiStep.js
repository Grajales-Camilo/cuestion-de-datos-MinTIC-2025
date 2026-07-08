import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ApiStep({ onNext, onPrev }) {
    const [hoveredCard, setHoveredCard] = useState(null);

    return (
        <div className="flex flex-col lg:flex-row items-center gap-12 max-w-7xl mx-auto h-full">

            {/* Left Column: Content */}
            <div className="flex-1 space-y-8 z-10 h-full overflow-y-auto pr-4 custom-scrollbar">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-4"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-4xl font-extrabold text-white">Motores de Inteligencia</h2>
                    </div>
                    <p className="text-lg text-slate-400">
                        Usamos algoritmos ActRAG para lograr una sinergia entre modelos de lenguaje avanzados y datos gubernamentales en tiempo real que permita aprovechar las políticas de datos abiertos con las necesidades sociales de los territorios.
                    </p>
                </motion.div>

                <motion.div
                    initial={{ height: 'auto', opacity: 1 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    className="overflow-hidden"
                >
                    <div className="bg-slate-800/80 backdrop-blur border border-slate-700 p-6 rounded-2xl space-y-4 text-slate-300 text-sm leading-relaxed shadow-xl">
                        <h3 className="text-cyan-400 font-bold text-lg mb-2">Pasos para el Buen Análisis de Datos</h3>
                        <p>Para aprovechar las herramientas basadas en datos, es crucial seguir un proceso estructurado para la toma de decisiones efectiva:</p>
                        <ol className="list-decimal list-inside space-y-2 marker:text-cyan-500">
                            <li><strong>Define bien tu problema:</strong> Es la piedra angular de todo proyecto/estudio. Si no está claro el "qué", no encontrarás el "cómo".</li>
                            <li><strong>Conoce tus datos:</strong> Identifica qué te falta y búscalo en los portales de datos abiertos. Si existe allá, la interactividad aquí será más eficiente.</li>
                            <li><strong>Identifica el set ideal:</strong> Estudia los metadatos, variables y diccionarios para entender el alcance.</li>
                            <li><strong>Reta tu análisis:</strong> Dice un adagio del análisis de datos: "Basura entra, basura sale". Valida tus hipótesis con pruebas críticas. Valida primero tus supuestos, y de ser necesario comparte algunas evidencias con nuestro chatbot.</li>
                            <li><strong>Escribe en formatos válidos:</strong> Asegura que tu evidencia sea accesible para los modelos en texto plano.</li>
                        </ol>

                        <div className="mt-6 pt-4 border-t border-slate-700">
                            <h4 className="text-white font-bold mb-3 flex items-center gap-2">
                                <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                Video Explicativo
                            </h4>
                            <div className="aspect-video bg-black rounded-lg overflow-hidden border border-slate-600 shadow-lg relative group">
                                <video
                                    controls
                                    className="w-full h-full object-cover"
                                    poster="/images/ai_brain.png"
                                >
                                    <source src="/videos/video_intro_BID.mp4" type="video/mp4" />
                                    Tu navegador no soporta el elemento de video.
                                </video>

                                {/* Fallback message if video is missing */}
                                <div className="absolute inset-0 flex items-center justify-center bg-black/80 -z-10">
                                    <p className="text-slate-500 text-xs">Carga tu video en /public/videos/video_intro_BID.mp4</p>
                                </div>
                            </div>
                            <p className="text-xs text-slate-500 mt-2 italic text-right">
                                Fuente: Banco Interamericano de Desarrollo (BID)
                            </p>
                        </div>
                    </div>
                </motion.div>

                <p className="text-sm text-slate-400 italic border-l-2 border-cyan-500 pl-4 py-2 bg-slate-800/30 rounded-r-lg">
                    Para utilizar nuestro sistema es necesario identificarse usando sus API Key de Gemini y Socrata. Para este demo ya hemos activado unas APIs públicas:
                </p>

                <div className="grid gap-6">
                    {/* Google Gemini Card */}
                    <div className="bg-slate-800/50 backdrop-blur-md rounded-2xl border border-slate-700 overflow-hidden">
                        <button
                            onClick={() => setHoveredCard(hoveredCard === 'gemini' ? null : 'gemini')}
                            className="w-full flex items-center justify-between p-6 text-left hover:bg-slate-800/80 transition-colors group"
                        >
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-blue-500/20 rounded-xl flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-white mb-1">Google Gemini Pro</h3>
                                    <div className="inline-flex items-center gap-2 px-2 py-1 bg-green-500/10 text-green-400 rounded text-[10px] font-bold uppercase tracking-wider border border-green-500/20">
                                        <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
                                        API Key Activa
                                    </div>
                                </div>
                            </div>
                            <svg className={`w-5 h-5 text-slate-500 transform transition-transform ${hoveredCard === 'gemini' ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                        </button>
                        <AnimatePresence>
                            {hoveredCard === 'gemini' && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="border-t border-slate-700 bg-slate-900/30"
                                >
                                    <div className="p-6 pt-4 text-sm text-slate-300 space-y-2">
                                        <p>Razonamiento semántico y generación de consultas SQL complejas.</p>
                                        <p className="text-xs text-slate-400 mt-2">
                                            <strong>Cómo activar su API Key:</strong> Para obtener tu API Key, visita <a href="https://aistudio.google.com/app/api-keys" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">Google AI Studio</a> crea un proyecto y genera una clave gratuita para desarrollo.
                                        </p>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* Socrata Card */}
                    <div className="bg-slate-800/50 backdrop-blur-md rounded-2xl border border-slate-700 overflow-hidden">
                        <button
                            onClick={() => setHoveredCard(hoveredCard === 'socrata' ? null : 'socrata')}
                            className="w-full flex items-center justify-between p-6 text-left hover:bg-slate-800/80 transition-colors group"
                        >
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-blue-500/20 rounded-xl flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
                                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4m0 5c0 2.21-3.58 4-8 4s-8-1.79-8-4" /></svg>
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-white mb-1">Socrata (SODA API)</h3>
                                    <div className="inline-flex items-center gap-2 px-2 py-1 bg-green-500/10 text-green-400 rounded text-[10px] font-bold uppercase tracking-wider border border-green-500/20">
                                        <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
                                        App Token Activo
                                    </div>
                                </div>
                            </div>
                            <svg className={`w-5 h-5 text-slate-500 transform transition-transform ${hoveredCard === 'socrata' ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                        </button>
                        <AnimatePresence>
                            {hoveredCard === 'socrata' && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="border-t border-slate-700 bg-slate-900/30"
                                >
                                    <div className="p-6 pt-4 text-sm text-slate-300 space-y-2">
                                        <p>Acceso directo a la "Hoja de Ruta Nacional de Datos Abiertos".</p>
                                        <p className="text-xs text-slate-400 mt-2">
                                            <strong>Cómo activar su API de Token:</strong> Para obtener tu App Token, regístrate en <a href="https://www.datos.gov.co/profile/edit/developer_settings" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">datos.gov.co</a>, haz clic en el botón "Crear nueva aplicación" (Create New App) y crea una nueva aplicación para obtener tus credenciales.
                                        </p>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>

                <div className="flex gap-4 pt-4">
                    <button
                        onClick={onPrev}
                        className="px-6 py-3 text-slate-400 hover:text-white font-medium transition-colors"
                    >
                        Atrás
                    </button>
                    <motion.button
                        whileHover={{ scale: 1.05, boxShadow: "0 0 20px rgba(59, 130, 246, 0.5)" }}
                        whileTap={{ scale: 0.95 }}
                        onClick={onNext}
                        className="px-10 py-5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-lg font-bold rounded-2xl shadow-xl shadow-blue-900/20 transition-all flex-1 flex items-center justify-center gap-4 group"
                    >
                        Siguiente
                        <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                        </svg>
                    </motion.button>
                </div>
            </div>

            {/* Right Column: Visuals */}
            <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.8 }}
                className="flex-1 relative flex justify-center items-center"
            >
                <div className="relative w-full max-w-md aspect-square">
                    {/* Glowing Orb Effect behind image */}
                    <div className="absolute inset-0 bg-blue-500/30 rounded-full blur-[80px] animate-pulse-slow"></div>

                    <img
                        src="/images/ai_brain.png"
                        alt="AI Brain"
                        className="relative z-10 w-full h-full object-contain drop-shadow-2xl animate-float mix-blend-screen"
                    />

                    {/* Floating Data Points */}
                    <div className="absolute top-10 right-10 p-3 bg-slate-900/80 backdrop-blur border border-cyan-500/30 rounded-lg shadow-lg animate-bounce-slow">
                        <div className="text-xs text-cyan-400 font-mono">SELECT * FROM salud_publica</div>
                    </div>
                    <div className="absolute bottom-20 left-0 p-3 bg-slate-900/80 backdrop-blur border border-purple-500/30 rounded-lg shadow-lg animate-bounce-slow delay-700">
                        <div className="text-xs text-purple-400 font-mono">WHERE municipio = 'Bogotá'</div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
