import React from 'react';

export default function InsightCard({ data, onCopy }) {
    // Intentamos inferir qué mostrar. 
    // Generalmente los datos vienen como { "columna": "valor" }
    // Tomaremos la primera clave numérica como valor principal, o la primera clave en general.

    const keys = Object.keys(data);
    const mainKey = keys.find(k => !isNaN(parseFloat(data[k]))) || keys[0];
    const value = data[mainKey];
    const label = mainKey.replace(/_/g, ' ').toUpperCase();

    // Otras claves para contexto
    const otherKeys = keys.filter(k => k !== mainKey);

    return (
        <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl p-5 text-white shadow-lg mb-4 relative overflow-hidden group">
            {/* Decorative background circle */}
            <div className="absolute -top-6 -right-6 w-24 h-24 bg-white opacity-10 rounded-full blur-xl group-hover:scale-150 transition-transform duration-500"></div>

            <div className="relative z-10">
                <p className="text-blue-100 text-xs font-semibold tracking-wider uppercase mb-1">{label}</p>
                <h3 className="text-3xl font-bold mb-3">{value}</h3>

                {otherKeys.length > 0 && (
                    <div className="space-y-1 mb-4">
                        {otherKeys.slice(0, 3).map(k => (
                            <p key={k} className="text-xs text-blue-200 truncate">
                                <span className="opacity-70">{k.replace(/_/g, ' ')}:</span> {data[k]}
                            </p>
                        ))}
                    </div>
                )}

                <button
                    onClick={() => {
                        const textToCopy = `Datos encontrados: ${label}: ${value}\n${otherKeys.map(k => `- ${k}: ${data[k]}`).join('\n')}`;
                        onCopy(textToCopy);
                    }}
                    className="w-full py-2 bg-white/20 hover:bg-white/30 backdrop-blur-sm rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    Copiar al Lienzo
                </button>
            </div>
        </div>
    );
}
