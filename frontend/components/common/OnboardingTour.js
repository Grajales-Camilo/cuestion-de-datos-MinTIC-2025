import React, { useState, useEffect } from 'react';
import Joyride, { ACTIONS, EVENTS, STATUS } from 'react-joyride';

export default function OnboardingTour({ run, setRun }) {
    useEffect(() => {
        // Check if user has seen the tour
        const hasSeenTour = localStorage.getItem('hasSeenTour');
        if (!hasSeenTour) {
            setRun(true);
        }
    }, [setRun]);

    const handleJoyrideCallback = (data) => {
        const { status } = data;
        const finishedStatuses = [STATUS.FINISHED, STATUS.SKIPPED];

        if (finishedStatuses.includes(status)) {
            setRun(false);
            localStorage.setItem('hasSeenTour', 'true');
        }
    };

    const steps = [
        {
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-lg text-slate-800">Bienvenido a Cuestión de Datos</h3>
                    <p className="text-slate-600 text-sm">
                        Este es tu copiloto para diseñar políticas públicas basadas en evidencia.
                    </p>
                </div>
            ),
            placement: 'center',
            target: 'body',
            disableBeacon: true,
        },
        {
            target: '#template-selector',
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-md text-slate-800">Seleccionar Metodología</h3>
                    <p className="text-slate-600 text-sm">
                        ⚡ No empieces desde cero. Elige una plantilla oficial (MGA, CONPES o Policy Brief) para pre-cargar la estructura estándar de tu documento.
                    </p>
                </div>
            ),
            placement: 'bottom',
            disableBeacon: true,
        },
        {
            target: '#section-problem_definition',
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-md text-slate-800">Empieza aquí</h3>
                    <p className="text-slate-600 text-sm">
                        Redacta tu hipótesis o problema en este recuadro.
                    </p>
                </div>
            ),
            placement: 'bottom',
        },
        {
            target: '#btn-investigate-problem_definition',
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-md text-slate-800">El Poder de la IA</h3>
                    <p className="text-slate-600 text-sm">
                        No necesitas buscar en Google. Haz clic en 'Investigar' y el Agente buscará datos en Socrata/DNP por ti.
                    </p>
                </div>
            ),
            placement: 'bottom',
        },
        {
            target: '#copilot-sidebar',
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-md text-slate-800">Tu Copiloto</h3>
                    <p className="text-slate-600 text-sm">
                        Aquí aparecerá la evidencia, gráficos y datos encontrados en tiempo real.
                    </p>
                </div>
            ),
            placement: 'left',
        },
        {
            target: '#btn-audit-problem_definition',
            content: (
                <div className="text-left space-y-2">
                    <h3 className="font-bold text-md text-slate-800">Auditoría</h3>
                    <p className="text-slate-600 text-sm">
                        Usa este botón si quieres que la IA critique tu propuesta y busque riesgos fiscales.
                    </p>
                </div>
            ),
            placement: 'bottom',
        },
    ];

    return (
        <Joyride
            steps={steps}
            run={run}
            continuous
            showSkipButton
            showProgress
            callback={handleJoyrideCallback}
            styles={{
                options: {
                    primaryColor: '#2563eb', // blue-600
                    zIndex: 10000,
                    arrowColor: '#fff',
                    backgroundColor: '#fff',
                    overlayColor: 'rgba(0, 0, 0, 0.6)',
                    textColor: '#334155', // slate-700
                    width: 400,
                },
                tooltip: {
                    borderRadius: '12px',
                    padding: '20px',
                    boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)', // shadow-xl
                },
                buttonNext: {
                    backgroundColor: '#2563eb',
                    fontSize: '14px',
                    fontWeight: 600,
                    padding: '10px 20px',
                    borderRadius: '8px',
                    outline: 'none',
                },
                buttonBack: {
                    color: '#64748b', // slate-500
                    marginRight: 10,
                    fontSize: '14px',
                    fontWeight: 500,
                },
                buttonSkip: {
                    color: '#94a3b8', // slate-400
                    fontSize: '14px',
                },
            }}
            locale={{
                back: 'Atrás',
                close: 'Cerrar',
                last: 'Finalizar',
                next: 'Siguiente',
                skip: 'Omitir',
            }}
        />
    );
}
