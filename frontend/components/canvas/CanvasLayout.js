import React from 'react';

export default function CanvasLayout({ children, sidebar, className = "" }) {
    return (
        <div className={`flex h-full w-full bg-slate-50 overflow-hidden text-slate-900 font-sans ${className}`}>
            {/* Main Content Area (Canvas) - Scrollable */}
            {/* Using w-full lg:w-2/3 to respect the 2/3 split requested */}
            <main className="flex-1 lg:w-2/3 h-full overflow-y-auto scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent min-w-0">
                <div className="max-w-5xl mx-auto p-6 lg:p-12 pb-32 space-y-8">
                    {children}
                </div>
            </main>

            {/* Sidebar Area (Copilot) - Fixed on right */}
            {/* Using lg:w-1/3 to respect the 1/3 split requested */}
            <aside className="hidden lg:flex flex-col lg:w-1/3 h-full bg-white border-l border-slate-200 shadow-[0_0_40px_-10px_rgba(0,0,0,0.1)] z-10 relative flex-none min-w-0">
                {sidebar}
            </aside>
        </div>
    );
}
