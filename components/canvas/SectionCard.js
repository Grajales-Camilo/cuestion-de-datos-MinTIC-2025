import React from 'react';
import RichTextEditor from './RichTextEditor';

export default function SectionCard({ id, title, content, placeholder, onChange, onInvestigate, onAudit }) {
    return (
        <div id={`section-${id}`} className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow duration-200 overflow-hidden group">
            <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                <h3 className="font-semibold text-lg text-slate-800">{title}</h3>
                <div className="flex gap-2">
                    <button
                        id={`btn-audit-${id}`}
                        onClick={onAudit}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        Auditar (Riesgos)
                    </button>
                    <button
                        id={`btn-investigate-${id}`}
                        onClick={onInvestigate}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        Investigar
                    </button>
                </div>
            </div>
            <div className="p-5 relative min-h-[200px]">
                <RichTextEditor
                    content={content}
                    onChange={onChange}
                    placeholder={placeholder}
                />
            </div>
        </div>
    );
}
