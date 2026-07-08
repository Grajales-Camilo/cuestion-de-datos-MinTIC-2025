import React, { useState } from 'react';
import Head from 'next/head';
import CanvasLayout from './CanvasLayout';
import CanvasHeader from './CanvasHeader';
import SectionCard from './SectionCard';
import TemplateSelector from './TemplateSelector';
import CopilotSidebar from '../copilot/CopilotSidebar';

import dynamic from 'next/dynamic';

const OnboardingTour = dynamic(
    () => import('../common/OnboardingTour'),
    { ssr: false }
);

export default function PolicyCanvasMain({ onBack }) {
    const [activeSectionId, setActiveSectionId] = useState('problem_definition');
    const [autoPrompt, setAutoPrompt] = useState(null);
    const [currentTemplateId, setCurrentTemplateId] = useState('custom');
    const [runTour, setRunTour] = useState(false);

    const [canvasState, setCanvasState] = useState({
        problem_definition: {
            id: 'problem_definition',
            title: 'Definición del Problema',
            content: '',
            placeholder: 'Describe claramente el problema público (ej: Alta desnutrición en La Guajira)...'
        },
        stakeholders: {
            id: 'stakeholders',
            title: 'Actores Involucrados',
            content: '',
            placeholder: 'Identifica a los afectados, beneficiarios y tomadores de decisiones...'
        },
        solution: {
            id: 'solution',
            title: 'Propuesta de Solución',
            content: '',
            placeholder: 'Describe la intervención propuesta...'
        },
        implementation: {
            id: 'implementation',
            title: 'Implementación y Recursos',
            content: '',
            placeholder: '¿Qué recursos técnicos y financieros se requieren?'
        }
    });

    const handleTemplateSelect = (template) => {
        setCurrentTemplateId(template.id);
        setCanvasState(template.sections);
        const firstSectionId = Object.keys(template.sections)[0];
        if (firstSectionId) setActiveSectionId(firstSectionId);
    };

    const handleSectionChange = (sectionId, newContent) => {
        setCanvasState(prev => ({
            ...prev,
            [sectionId]: { ...prev[sectionId], content: newContent }
        }));
    };

    const handleAskCopilot = (context) => {
        setActiveSectionId(context.sectionId);
        const { sectionTitle, currentContent } = context;
        let prompt = "";

        if (!currentContent || currentContent.trim().length < 5) {
            prompt = `Estoy trabajando en la sección "${sectionTitle}" de una política pública. No tengo datos aún. ¿Podrías buscar en Socrata indicadores clave o datos relevantes en Colombia para empezar a redactar esto? Múestrame ejemplos.`;
        } else {
            prompt = `Actúa como analista de datos. Estoy redactando la sección "${sectionTitle}".
      
      Mi borrador dice: "${currentContent}".
      
      Por favor:
      1. Identifica los municipios, departamentos o temas clave en mi texto.
      2. Busca en los datasets oficiales (Salud, Sisbén, APC, etc.) datos que confirmen o refuten mi planteamiento.
      3. Muéstrame una tabla o dato destacado con la evidencia.`;
        }
        setAutoPrompt(prompt);
    };

    const handleAuditSection = (sectionId, content) => {
        setActiveSectionId(sectionId);
        const prompt = `Actúa como un auditor fiscal crítico. Analiza esta propuesta: '${content}'. Busca en Socrata datos de proyectos fallidos, presupuestos no ejecutados o indicadores que sugieran que esto es mala idea. Adviérteme de los riesgos.`;
        setAutoPrompt(prompt);
    };

    const handleApplyDataToCanvas = (dataString) => {
        setCanvasState(prev => {
            const currentContent = prev[activeSectionId].content;
            const newContent = currentContent
                ? `${currentContent}\n\n[EVIDENCIA DE DATOS]:\n${dataString}`
                : dataString;
            return {
                ...prev,
                [activeSectionId]: { ...prev[activeSectionId], content: newContent }
            };
        });
    };

    return (
        <>
            <Head>
                <title>Policy Canvas | Cuestión de Datos</title>
            </Head>

            <OnboardingTour run={runTour} setRun={setRunTour} />

            <CanvasLayout
                className="pt-16" // Added padding-top to prevent overlap with fixed header
                sidebar={
                    <CopilotSidebar
                        externalTrigger={autoPrompt}
                        onResetTrigger={() => setAutoPrompt(null)}
                        onApplyData={handleApplyDataToCanvas}
                    />
                }
            >
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-4">
                        {onBack && (
                            <button
                                onClick={onBack}
                                className="flex items-center gap-2 text-slate-500 hover:text-blue-600 transition-colors text-sm font-medium px-3 py-2 rounded-lg hover:bg-slate-100"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                                Volver al Wizard
                            </button>
                        )}
                    </div>
                    <button
                        onClick={() => setRunTour(true)}
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Volver a ver el tutorial
                    </button>
                </div>

                <CanvasHeader
                    title="Policy Canvas"
                    subtitle="Diseña, analiza y mejora políticas públicas con el poder de los datos y la IA."
                >
                    <TemplateSelector
                        onSelectTemplate={handleTemplateSelect}
                        currentTemplateId={currentTemplateId}
                    />
                </CanvasHeader>

                <div className="grid grid-cols-1 gap-6">
                    {Object.values(canvasState).map((section) => (
                        <SectionCard
                            key={section.id}
                            id={section.id}
                            title={section.title}
                            content={section.content}
                            placeholder={section.placeholder}
                            onChange={(value) => handleSectionChange(section.id, value)}
                            onInvestigate={() => handleAskCopilot({
                                sectionId: section.id,
                                sectionTitle: section.title,
                                currentContent: section.content
                            })}
                            onAudit={() => handleAuditSection(section.id, section.content)}
                        />
                    ))}
                </div>
            </CanvasLayout>
        </>
    );
}
