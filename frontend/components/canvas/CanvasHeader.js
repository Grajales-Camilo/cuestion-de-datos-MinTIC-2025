import React from 'react';

export default function CanvasHeader({ title, subtitle, children }) {
    return (
        <header className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
                <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{title}</h1>
                {subtitle && <p className="mt-2 text-lg text-slate-500">{subtitle}</p>}
            </div>
            {children}
        </header>
    );
}
