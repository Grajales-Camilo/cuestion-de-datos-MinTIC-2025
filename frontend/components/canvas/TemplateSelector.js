import React, { useState } from 'react';
import { POLICY_TEMPLATES } from '../../data/policyTemplates';

export default function TemplateSelector({ onSelectTemplate, currentTemplateId }) {
    const [isOpen, setIsOpen] = useState(false);

    const handleSelect = (templateKey) => {
        onSelectTemplate(POLICY_TEMPLATES[templateKey]);
        setIsOpen(false);
    };

    return (
        <div id="template-selector" className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 text-slate-700 font-medium transition-all"
            >
                <svg className="w-5 h-5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                </svg>
                <span>Plantilla: {Object.values(POLICY_TEMPLATES).find(t => t.id === currentTemplateId)?.name || 'Personalizada'}</span>
                <svg className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-20"
                        onClick={() => setIsOpen(false)}
                    ></div>
                    <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-slate-100 z-30 overflow-hidden animate-fade-in-up">
                        <div className="p-3 bg-slate-50 border-b border-slate-100">
                            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Seleccionar Metodología</h4>
                        </div>
                        <div className="p-2 space-y-1">
                            {Object.entries(POLICY_TEMPLATES).map(([key, template]) => (
                                <button
                                    key={key}
                                    onClick={() => handleSelect(key)}
                                    className={`w-full text-left p-3 rounded-lg transition-colors flex flex-col gap-1 ${currentTemplateId === template.id
                                        ? 'bg-indigo-50 border border-indigo-100'
                                        : 'hover:bg-slate-50 border border-transparent'
                                        }`}
                                >
                                    <span className={`font-medium text-sm ${currentTemplateId === template.id ? 'text-indigo-700' : 'text-slate-700'
                                        }`}>
                                        {template.name}
                                    </span>
                                    <span className="text-xs text-slate-500">
                                        {template.description}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
