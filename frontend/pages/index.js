import Head from "next/head";
import {
  Search,
  ShieldCheck,
  FileCheck2,
  Quote,
  ChevronRight,
} from "lucide-react";
import { Button, Card, CardBody } from "../components/ui";
import { taglineFont } from "../lib/design/taglineFont";

const CONFIANZA_CHAIN = ["Dataset", "Entidad", "Consulta", "Validación", "Cifra"];

const PASOS = [
  {
    icon: Search,
    titulo: "Preguntas o señalas una sección",
    texto:
      "Escribes una pregunta libre o disparas la investigación desde una sección de tu documento de política pública.",
  },
  {
    icon: FileCheck2,
    titulo: "El agente investiga el catálogo",
    texto:
      "Un agente de varios pasos busca en el catálogo completo de datos.gov.co y ejecuta la consulta necesaria, nunca sobre una lista fija de datasets.",
  },
  {
    icon: ShieldCheck,
    titulo: "Cada dato pasa validación de calidad",
    texto:
      "Esquema, completitud, temporalidad y trazabilidad se verifican antes de que cualquier evidencia se muestre.",
  },
  {
    icon: Quote,
    titulo: "Insertas la evidencia con su cita",
    texto:
      "Tabla, narrativa citable y cita completa (dataset, entidad, consulta, fecha) se insertan en tu documento, listo para exportar a Word.",
  },
];

export default function Home() {
  return (
    <div className="cdt-v2 flex min-h-screen flex-col bg-cdt-white">
      <Head>
        <title>Cuestión de Datos — Evidencia trazable para política pública</title>
        <meta
          name="description"
          content="Encuentra, consulta y valida evidencia cuantitativa del catálogo de datos abiertos del Estado colombiano, con trazabilidad completa: dataset, entidad, consulta y fecha."
        />
      </Head>

      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-cdt-4 focus:top-cdt-4 focus:z-50 focus:rounded-cdt-md focus:bg-cdt-blue-900 focus:px-cdt-4 focus:py-cdt-2 focus:text-cdt-white"
      >
        Saltar al contenido
      </a>

      <header className="flex items-center justify-between border-b border-cdt-blue-100 bg-cdt-blue-50 px-cdt-4 py-cdt-3 sm:px-cdt-8">
        <h1 className="text-cdt-lg font-cdt-bold text-cdt-blue-900">
          Cuestión de Datos{" "}
          <span className={`${taglineFont.className} text-cdt-xl text-cdt-blue-700 opacity-70`}>
            - #AI for good
          </span>
        </h1>
        <Button as="a" href="/app" variant="primary">
          Abrir el lienzo
        </Button>
      </header>

      <main id="contenido" tabIndex={-1} className="flex-1">
        {/* Hero */}
        <section className="px-cdt-4 py-cdt-16 sm:px-cdt-8">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-cdt-sm font-cdt-bold uppercase tracking-wide text-cdt-blue-700">
              Copiloto de evidencia para política pública
            </p>
            <h2 className="mt-cdt-4 text-cdt-2xl font-cdt-bold leading-cdt-tight text-cdt-slate-900">
              Cada cifra de tu documento, con su fuente a la vista
            </h2>
            <p className="mx-auto mt-cdt-4 max-w-2xl text-cdt-base leading-cdt-relaxed text-cdt-slate-600">
              Cuestión de Datos investiga el catálogo de datos abiertos del Estado
              colombiano y entrega cada cifra con su cadena de trazabilidad
              completa. Cuando no hay evidencia elegible, lo dice explícitamente
              en vez de estimar.
            </p>
            <div className="mt-cdt-8 flex flex-col items-center justify-center gap-cdt-3 sm:flex-row">
              <Button as="a" href="/app" variant="primary" className="w-full sm:w-auto">
                Abrir el lienzo de políticas
              </Button>
              <Button
                as="a"
                href="#como-funciona"
                variant="secondary"
                className="w-full sm:w-auto"
              >
                Ver cómo funciona
              </Button>
            </div>

            <Card className="mx-auto mt-cdt-12 max-w-xl bg-cdt-blue-50/60">
              <CardBody>
                <p className="text-cdt-xs font-cdt-bold uppercase tracking-wide text-cdt-blue-900">
                  La cadena de confianza detrás de cada cifra
                </p>
                <div className="mt-cdt-3 flex flex-wrap items-center justify-center gap-cdt-2">
                  {CONFIANZA_CHAIN.map((eslabon, index) => (
                    <span key={eslabon} className="flex items-center gap-cdt-2">
                      <span className="rounded-cdt-full bg-cdt-blue-100 px-cdt-3 py-cdt-1 text-cdt-xs font-cdt-bold text-cdt-blue-900">
                        {eslabon}
                      </span>
                      {index < CONFIANZA_CHAIN.length - 1 ? (
                        <ChevronRight
                          className="h-4 w-4 text-cdt-blue-500"
                          aria-hidden="true"
                          focusable="false"
                        />
                      ) : null}
                    </span>
                  ))}
                </div>
              </CardBody>
            </Card>
          </div>
        </section>

        {/* Cómo funciona */}
        <section
          id="como-funciona"
          className="border-t border-cdt-blue-100 bg-cdt-blue-50 px-cdt-4 py-cdt-16 sm:px-cdt-8"
        >
          <div className="mx-auto max-w-3xl">
            <h2 className="text-center text-cdt-xl font-cdt-bold text-cdt-slate-900">
              Cómo funciona
            </h2>
            <ol className="relative mt-cdt-10 flex flex-col gap-cdt-8 border-l border-cdt-blue-100 pl-cdt-6">
              {PASOS.map((paso, index) => {
                const Icon = paso.icon;
                return (
                  <li key={paso.titulo} className="relative">
                    <span
                      className="absolute -left-[calc(1.5rem+9px)] flex h-cdt-6 w-cdt-6 items-center justify-center rounded-cdt-full bg-cdt-blue-700 text-cdt-white"
                      aria-hidden="true"
                    >
                      <Icon className="h-3.5 w-3.5" focusable="false" />
                    </span>
                    <p className="text-cdt-sm font-cdt-bold text-cdt-blue-900">
                      {index + 1}. {paso.titulo}
                    </p>
                    <p className="mt-cdt-1 text-cdt-base leading-cdt-relaxed text-cdt-slate-600">
                      {paso.texto}
                    </p>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        {/* Confianza y honestidad */}
        <section className="px-cdt-4 py-cdt-16 sm:px-cdt-8">
          <div className="mx-auto grid max-w-3xl gap-cdt-6 sm:grid-cols-2">
            <Card>
              <CardBody>
                <p className="text-cdt-sm font-cdt-bold text-cdt-blue-900">Cero fabricación</p>
                <p className="mt-cdt-2 text-cdt-base leading-cdt-relaxed text-cdt-slate-600">
                  Ninguna cifra se presenta sin evidencia trazable. Si no hay
                  evidencia elegible en el catálogo, el sistema lo dice
                  explícitamente en vez de estimar.
                </p>
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <p className="text-cdt-sm font-cdt-bold text-cdt-blue-900">
                  Sin cuentas de usuario
                </p>
                <p className="mt-cdt-2 text-cdt-base leading-cdt-relaxed text-cdt-slate-600">
                  El acceso a una investigación guardada usa un token de alcance
                  mínimo y expirable por corrida. Antes de tu primera
                  investigación te decimos qué se guarda, para qué, por cuánto
                  tiempo y cómo borrarlo.
                </p>
              </CardBody>
            </Card>
          </div>
        </section>
      </main>

      <footer className="border-t border-cdt-blue-100 px-cdt-4 py-cdt-6 text-center sm:px-cdt-8">
        <p className="text-cdt-xs text-cdt-slate-400">Cuestión de Datos</p>
      </footer>
    </div>
  );
}
