import React, { useState } from 'react';
import Head from 'next/head';
import { motion, AnimatePresence } from 'framer-motion';
import IntroStep from '../components/wizard/IntroStep';
import ApiStep from '../components/wizard/ApiStep';
import DatabaseStep from '../components/wizard/DatabaseStep';
import PolicyCanvasMain from '../components/canvas/PolicyCanvasMain';
import HelpStep from '../components/wizard/HelpStep';

export default function Home() {
  const [currentStep, setCurrentStep] = useState(0);
  const [direction, setDirection] = useState(0); // 1 for next, -1 for prev

  const nextStep = () => {
    setDirection(1);
    setCurrentStep(prev => prev + 1);
  };

  const prevStep = () => {
    setDirection(-1);
    setCurrentStep(prev => Math.max(0, prev - 1));
  };

  const goToStep = (step) => {
    if (step === currentStep) return;
    setDirection(step > currentStep ? 1 : -1);
    setCurrentStep(step);
  };

  // Variants for slide animation
  const variants = {
    enter: (direction) => ({
      x: direction > 0 ? 1000 : -1000,
      opacity: 0
    }),
    center: {
      zIndex: 1,
      x: 0,
      opacity: 1
    },
    exit: (direction) => ({
      zIndex: 0,
      x: direction < 0 ? 1000 : -1000,
      opacity: 0
    })
  };

  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-50 overflow-hidden relative selection:bg-cyan-500 selection:text-slate-900">
      <Head>
        <title>Cuestión de Datos | AI Policy Lab</title>
        <meta name="description" content="Plataforma de formulación de políticas públicas basada en evidencia." />
      </Head>

      {/* Background Effects */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/20 rounded-full blur-[120px] animate-pulse-slow"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/20 rounded-full blur-[120px] animate-pulse-slow delay-1000"></div>
      </div>

      {/* Wizard Header / Progress */}
      <header className="fixed top-0 left-0 right-0 bg-slate-900/80 backdrop-blur-md border-b border-white/10 z-50 h-20 flex items-center justify-between px-8 shadow-2xl">
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => goToStep(0)}>
          <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-cyan-500 rounded-xl flex items-center justify-center text-white font-bold shadow-lg shadow-blue-500/20">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
          </div>
          <div>
            <h1 className="font-bold text-lg tracking-tight text-white">Cuestión de Datos</h1>
            <p className="text-[10px] text-cyan-400 font-mono tracking-widest uppercase">MinTIC • ActRAG para políticas públicas</p>
          </div>
        </div>

        {/* Navigation Dots */}
        <div className="flex items-center gap-4">
          {[0, 1, 2, 3, 4].map((step) => (
            <button
              key={step}
              onClick={() => goToStep(step)}
              className="group relative flex flex-col items-center gap-2 focus:outline-none"
            >
              <div
                className={`w-3 h-3 rounded-full transition-all duration-500 z-10 ${step === currentStep
                  ? 'bg-cyan-400 scale-125 shadow-[0_0_10px_rgba(34,211,238,0.8)]'
                  : step < currentStep
                    ? 'bg-blue-600'
                    : 'bg-slate-700 group-hover:bg-slate-600'
                  }`}
              />
              {step < 4 && (
                <div
                  className={`absolute top-1.5 left-[50%] w-[calc(100%+1rem)] h-0.5 -z-0 transition-colors duration-500 ${step < currentStep ? 'bg-blue-600' : 'bg-slate-800'
                    }`}
                />
              )}
              <span className={`text-[10px] font-medium transition-colors ${step === currentStep ? 'text-cyan-400' : 'text-slate-500'
                }`}>
                {['Intro', 'Motores', 'Datos', 'Lienzo', 'Ayuda'][step]}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-4">
          {currentStep > 0 && (
            <button
              onClick={prevStep}
              className="text-slate-400 hover:text-white transition-colors text-sm font-medium px-4 py-2"
            >
              Atrás
            </button>
          )}
          <div className="text-xs text-slate-500 font-mono border border-slate-800 px-2 py-1 rounded bg-slate-900">
            v0.1.1-beta
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className={`pt-24 pb-12 px-6 min-h-screen flex flex-col relative z-10 ${currentStep === 3 ? '' : 'justify-center'}`}>
        <AnimatePresence initial={false} custom={direction} mode="wait">
          {currentStep === 0 && (
            <motion.div
              key="step0"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 }
              }}
              className="w-full"
            >
              <IntroStep onNext={nextStep} />
            </motion.div>
          )}

          {currentStep === 1 && (
            <motion.div
              key="step1"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 }
              }}
              className="w-full h-full"
            >
              <ApiStep onNext={nextStep} onPrev={prevStep} />
            </motion.div>
          )}

          {currentStep === 2 && (
            <motion.div
              key="step2"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 }
              }}
              className="w-full h-full"
            >
              <DatabaseStep onNext={nextStep} onPrev={prevStep} />
            </motion.div>
          )}

          {currentStep === 3 && (
            <motion.div
              key="step3"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 }
              }}
              className="w-full h-full"
            >
              {/* Renderizamos el Canvas dentro del layout del Wizard pero ajustando su altura */}
              <div className="h-[calc(100vh-8rem)] rounded-2xl overflow-hidden border border-slate-800 shadow-2xl">
                <PolicyCanvasMain onBack={prevStep} />
              </div>
            </motion.div>
          )}

          {currentStep === 4 && (
            <motion.div
              key="step4"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 }
              }}
              className="w-full h-full"
            >
              <HelpStep onPrev={() => goToStep(3)} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}