// components/copilot/CopilotSidebar.js
import React, { useState, useRef, useEffect } from 'react';
import InsightCard from './InsightCard';

// Recibimos externalTrigger y onResetTrigger
export default function CopilotSidebar({ externalTrigger, onResetTrigger, onApplyData }) {
    const [messages, setMessages] = useState([
        {
            id: 1,
            role: 'system',
            content: 'Hola, soy tu Copiloto de Políticas Públicas. Escribe en el lienzo y presiona "Investigar" para que busque evidencia automáticamente.'
        }
    ]);
    const [isLoading, setIsLoading] = useState(false);
    const [input, setInput] = useState('');
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // --- EFECTO MÁGICO: ESCUCHAR AL PADRE ---
    useEffect(() => {
        if (externalTrigger) {
            handleSend(externalTrigger); // Enviamos el prompt automático
            if (onResetTrigger) onResetTrigger(); // Apagamos el gatillo
        }
    }, [externalTrigger]);
    // ----------------------------------------

    const handleSend = async (text) => {
        if (!text.trim()) return;

        const userMsg = { id: Date.now(), role: 'user', content: text };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await fetch('/api/consultar_v2', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pregunta: text })
            });

            const data = await response.json();

            const botMsg = {
                id: Date.now() + 1,
                role: 'assistant',
                content: data.explanation || "Aquí tienes los resultados encontrados:",
                results: data.resultados || []
            };

            setMessages(prev => [...prev, botMsg]);

        } catch (error) {
            console.error("Error consultando agente:", error);
            setMessages(prev => [...prev, {
                id: Date.now() + 1,
                role: 'assistant',
                content: 'Error de conexión con el Agente.'
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    // Renderizado de resultados (Tabla o InsightCard)
    const renderResult = (result) => {
        const { datos } = result;
        if (!datos || datos.length === 0) return <p className="text-sm text-slate-500 italic mt-2 bg-slate-100 p-2 rounded">No se encontraron datos exactos para esta búsqueda en Socrata.</p>;

        if (datos.length === 1) {
            return <InsightCard data={datos[0]} onCopy={onApplyData} />;
        }

        if (datos.length > 1) {
            const headers = Object.keys(datos[0]);
            return (
                <div className="mt-3 bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
                    <div className="overflow-x-auto max-w-full">
                        <table className="min-w-full text-xs text-left">
                            <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    {headers.map(h => (
                                        <th key={h} className="px-3 py-2 font-medium text-slate-600 uppercase tracking-wider">{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {datos.slice(0, 5).map((row, i) => (
                                    <tr key={i} className="hover:bg-slate-50 transition-colors">
                                        {headers.map(h => (
                                            <td key={h} className="px-3 py-2 text-slate-700 whitespace-nowrap max-w-[150px] truncate" title={row[h]}>
                                                {row[h]}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <button
                        onClick={() => onApplyData(JSON.stringify(datos, null, 2))}
                        className="w-full py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-bold transition-colors border-t border-blue-100 flex items-center justify-center gap-2"
                    >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        Copiar Tabla al Lienzo
                    </button>
                </div>
            );
        }
    };

    return (
        <div id="copilot-sidebar" className="flex flex-col h-full bg-slate-50 border-l border-slate-200">
            {/* Header */}
            <div className="p-4 bg-white border-b border-slate-200 shadow-sm z-10 flex justify-between items-center">
                <div>
                    <h2 className="font-bold text-slate-800 flex items-center gap-2 text-sm">
                        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                        Agente de Datos
                    </h2>
                    <p className="text-[10px] text-slate-400 font-mono">SOCRATA API V2.1 ACTIVE</p>
                </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {messages.map((msg) => (
                    <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                        <div className={`max-w-[95%] rounded-2xl px-4 py-3 text-sm shadow-sm ${msg.role === 'user'
                            ? 'bg-blue-600 text-white rounded-br-none'
                            : 'bg-white border border-slate-200 text-slate-700 rounded-bl-none'
                            }`}>
                            <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                        </div>

                        {/* Resultados */}
                        {msg.results && msg.results.length > 0 && (
                            <div className="w-full mt-2 pl-1 animate-fade-in-up">
                                {msg.results.map((res, idx) => (
                                    <div key={idx} className="mb-4">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="text-[10px] font-bold bg-slate-200 text-slate-600 px-2 py-0.5 rounded uppercase tracking-wider">
                                                Fuente: {res.dataset_id}
                                            </span>
                                        </div>
                                        {renderResult(res)}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
                {isLoading && (
                    <div className="flex items-start animate-pulse">
                        <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm flex gap-2 items-center">
                            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce delay-75"></div>
                            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce delay-150"></div>
                            <span className="text-xs text-slate-400 ml-2">Analizando metadatos...</span>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 bg-white border-t border-slate-200">
                <div className="relative">
                    <input
                        type="text"
                        placeholder="Escribe una pregunta manual..."
                        className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all outline-none text-sm"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSend(input);
                            }
                        }}
                    />
                    <button
                        onClick={() => handleSend(input)}
                        disabled={isLoading || !input.trim()}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
}