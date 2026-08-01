import { useState } from "react";
import Head from "next/head";
import { CheckCircle2, Trash2, FileSearch } from "lucide-react";
import {
  Button,
  IconButton,
  Badge,
  Card,
  CardHeader,
  CardBody,
  CardFooter,
  Disclosure,
  Modal,
  Tabs,
  Table,
  LiveRegion,
  Skeleton,
  VisuallyHidden,
} from "../../components/ui";
import { messageForNode } from "../../lib/agent/messages.es";
import { devOnlyGetStaticProps } from "../../lib/gallery/devOnlyGuard";
import { useAgentRun } from "../../hooks/useAgentRun";
import { usePolitePolite } from "../../hooks/usePolitePolite";
import { RUN_STATUS } from "../../lib/agent/runStates";
import {
  CopilotPanel,
  QuestionComposer,
  IntentSummary,
  RunTimeline,
  ConnectionStatus,
  TerminalPanel,
} from "../../components/agent";
import { DEMO_SCENARIOS, makeDemoAgentClient } from "../../lib/gallery/agentDemoScenarios";

/**
 * Galería interna del sistema visual v2 ("Pulso por lo Público"). Existe
 * solo para revisar primitivas, variantes y estados durante el desarrollo
 * de F1/F3 — nunca es una superficie de producto. `getStaticProps` la
 * convierte en 404 fuera de desarrollo (ver función al final del archivo).
 *
 * La composición estática de "ruta central" (F1-01) sigue sin usar
 * streamRun/agentClient/runReducer: es texto y números fijos. La sección
 * "AgentDemo" (F3-7A), en cambio, SÍ usa `useAgentRun`/`usePolitePolite`
 * reales con dobles de transporte (`lib/gallery/agentDemoScenarios.js`)
 * que reproducen eventos de corridas reales capturadas — nunca hace POST,
 * SSE ni DELETE de red real.
 */

const TOKENS = [
  { name: "blue-900", hex: "#004E8C", className: "bg-cdt-blue-900" },
  { name: "blue-700", hex: "#0068A8", className: "bg-cdt-blue-700" },
  { name: "blue-500", hex: "#1F7EE0", className: "bg-cdt-blue-500" },
  { name: "blue-100", hex: "#CDE8FF", className: "bg-cdt-blue-100" },
  { name: "blue-50", hex: "#F3F9FF", className: "bg-cdt-blue-50" },
  { name: "white", hex: "#FFFFFF", className: "bg-cdt-white border border-cdt-blue-100" },
  { name: "slate-900", hex: "#0F172A", className: "bg-cdt-slate-900" },
  { name: "slate-600", hex: "#475569", className: "bg-cdt-slate-600" },
  { name: "slate-400", hex: "#94A3B8", className: "bg-cdt-slate-400" },
  { name: "success", hex: "#15803D", className: "bg-cdt-success" },
  { name: "warning", hex: "#B45309", className: "bg-cdt-warning" },
  { name: "error", hex: "#B91C1C", className: "bg-cdt-error" },
];

// Los 9 eventos "step" reales del fixture (id 1–9 de
// completed-stream.sse.txt), traducidos con el mismo diccionario real que
// usará F2/F3 (frontend/lib/agent/messages.es.js) — no se reescriben a mano.
const REAL_STEPS = [
  { node: "start", elapsed: null },
  { node: "select_candidate", elapsed: "3,3 s" },
  { node: "profile_dataset", elapsed: "3,3 s" },
  { node: "build_plan", elapsed: "3,4 s" },
  { node: "explore_value", elapsed: "6,4 s" },
  { node: "build_plan", elapsed: "7,4 s" },
  { node: "execute_query", elapsed: "9,3 s" },
  { node: "synthesize", elapsed: "9,5 s" },
  { node: "complete", elapsed: "11,7 s" },
];

const REAL_QUESTION =
  "¿Cuál fue el promedio de deserción escolar en el departamento de Antioquia entre 2018 y 2022?";
const REAL_CLAIM_DISPLAY_VALUE = "3,9660000000000000"; // valor real de la corrida, sin redondear
const REAL_EVIDENCE_ROW = { metric_avg_1: "3.9660000000000000" };
const REAL_DATASET_NAME = "MEN_ESTADISTICAS_EN_EDUCACION_EN_PREESCOLAR, BÁSICA Y MEDIA_POR_DEPARTAMENTO";
const REAL_PUBLISHER = "Ministerio de Educación Nacional";
const REAL_SOQL =
  "SELECT avg(desercion) AS metric_avg_1 WHERE departamento = 'Antioquia' AND (ano >= 2018 AND ano <= 2022) LIMIT 100 OFFSET 0";
const REAL_DATA_CUTOFF = "2025-11-13";

/**
 * Muestra funcional de F3-7A: useAgentRun + usePolitePolite reales,
 * conectados a los componentes de `components/agent/*`, con un cliente y
 * un `streamRunner` dobles (`agentDemoScenarios.js`) que reproducen
 * eventos de corridas reales — nunca red real. `consentGranted` es
 * siempre `true` aquí porque F3-7A no incluye el flujo de consentimiento
 * (RF-802, F3-7B); no hay atajo de producción oculto: el gate real
 * (`consentGranted !== true` en `useAgentRun`) sigue activo, esta demo
 * simplemente ya lo satisface con una prop fija.
 */
function AgentDemoSection() {
  const [scenarioKey, setScenarioKey] = useState("completado");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const demoClient = useState(() => makeDemoAgentClient())[0];
  const scenario = DEMO_SCENARIOS[scenarioKey];

  const { state, start, detach, reset } = useAgentRun({
    baseUrl: "http://demo.invalid", // nunca se usa: streamRunner/agentClient son dobles
    consentGranted: true,
    agentClient: demoClient,
    streamRunner: scenario.streamRunner,
  });
  const { message } = usePolitePolite({ state });

  function handleSubmit({ question, contextHint }) {
    reset();
    start({ question, contextHint });
  }

  return (
    <Section id="agent-demo" title="Muestra funcional — useAgentRun + componentes del copiloto (F3-7A)">
      <p className="max-w-2xl text-cdt-sm text-cdt-slate-600">
        A diferencia de la composición estática de arriba, esto SÍ es{" "}
        <code>useAgentRun</code>/<code>usePolitePolite</code> reales conectados a{" "}
        <code>CopilotPanel</code>, <code>RunTimeline</code>, <code>ConnectionStatus</code> y{" "}
        <code>TerminalPanel</code> reales. El transporte es un doble que reproduce eventos de
        corridas reales capturadas (<code>tests/fixtures/*.json</code>) con pausas cortas — nunca
        hace una llamada de red.
      </p>

      <div className="flex flex-wrap items-center gap-cdt-2">
        <span className="text-cdt-xs font-cdt-bold text-cdt-slate-600">Escenario:</span>
        {Object.entries(DEMO_SCENARIOS).map(([key, { label }]) => (
          <Button
            key={key}
            variant={key === scenarioKey ? "primary" : "secondary"}
            onClick={() => {
              detach();
              setScenarioKey(key);
            }}
          >
            {label}
          </Button>
        ))}
        <Button variant="quiet" onClick={() => setCopilotOpen(true)}>
          Abrir copiloto
        </Button>
      </div>

      <LiveRegion message={message} />

      <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} title="Copiloto — muestra F3-7A">
        <div className="flex flex-col gap-cdt-4">
          <QuestionComposer onSubmit={handleSubmit} consentGranted disabled={state.status === RUN_STATUS.CREATING} />
          {state.status === RUN_STATUS.CREATING ? (
            <p role="status" className="text-cdt-sm font-cdt-bold text-cdt-blue-700">
              Preparando la investigación…
            </p>
          ) : null}
          <ConnectionStatus
            status={state.status}
            reconnectAttempt={state.reconnect.attempts}
            onRetry={() => start({ question: state.question, contextHint: state.contextHint })}
          />
          <IntentSummary intention={state.intention} onReformulate={reset} />
          <RunTimeline steps={state.steps} status={state.status} />
          <TerminalPanel state={state} onRestart={reset} />
        </div>
      </CopilotPanel>
    </Section>
  );
}

function Section({ id, title, children }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="mb-cdt-12">
      <h2 id={`${id}-heading`} className="mb-cdt-4 text-cdt-xl font-cdt-bold text-cdt-blue-900">
        {title}
      </h2>
      <div className="flex flex-col gap-cdt-6">{children}</div>
    </section>
  );
}

export default function UiGalleryPage() {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div className="cdt-v2 min-h-screen bg-cdt-white px-cdt-4 py-cdt-8 sm:px-cdt-8">
      <Head>
        <title>Galería de componentes — Frontend v2 (solo desarrollo)</title>
        <meta name="robots" content="noindex, nofollow" />
      </Head>

      <header className="mb-cdt-10 max-w-3xl">
        <p className="mb-cdt-1 text-cdt-xs font-cdt-bold uppercase tracking-wide text-cdt-slate-600">
          Solo disponible en desarrollo
        </p>
        <h1 className="mb-cdt-2 text-cdt-2xl font-cdt-bold text-cdt-blue-900">
          Galería de componentes — Frontend v2
        </h1>
        <p className="text-cdt-base text-cdt-slate-600">
          Sistema visual «Pulso por lo Público» (F1-01). Muestra las primitivas
          accesibles de <code>frontend/components/ui</code> con sus variantes y
          estados. No es la aplicación funcional; ningún componente aquí llama
          al backend, al SSE ni al reducer.
        </p>
      </header>

      <Section id="colores" title="Colores — 12 tokens fijos">
        <div className="grid grid-cols-2 gap-cdt-4 sm:grid-cols-3 md:grid-cols-4">
          {TOKENS.map((token) => (
            <div key={token.name} className="flex flex-col gap-cdt-2">
              <div className={`h-16 rounded-cdt-md ${token.className}`} aria-hidden="true" />
              <div>
                <p className="text-cdt-sm font-cdt-bold text-cdt-slate-900">{token.name}</p>
                <p className="text-cdt-xs text-cdt-slate-600">{token.hex}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section id="tipografia" title="Tipografía — una familia, dos pesos">
        <p className="text-cdt-2xl font-cdt-bold text-cdt-slate-900">Texto 2xl / bold — títulos de sección</p>
        <p className="text-cdt-xl font-cdt-bold text-cdt-slate-900">Texto xl / bold — subtítulos</p>
        <p className="text-cdt-lg font-cdt-normal text-cdt-slate-900">Texto lg / normal — encabezados menores</p>
        <p className="text-cdt-base font-cdt-normal text-cdt-slate-900">
          Texto base / normal — cuerpo de párrafo, el tamaño más usado en la interfaz.
        </p>
        <p className="text-cdt-sm font-cdt-bold text-cdt-slate-600">Texto sm / bold — etiquetas, botones</p>
        <p className="text-cdt-xs font-cdt-normal text-cdt-slate-600">
          Texto xs / normal — metadatos, pie. (<code>slate-400</code> no aparece aquí: no cumple 4.5:1 como
          texto legible — solo sirve para elementos decorativos o deshabilitados, ver swatch en «Colores».)
        </p>
      </Section>

      <Section id="botones" title="Button">
        <div className="flex flex-wrap items-center gap-cdt-3">
          <Button variant="primary">Primaria</Button>
          <Button variant="secondary">Secundaria</Button>
          <Button variant="quiet">Silenciosa</Button>
          <Button variant="destructive">Destructiva</Button>
        </div>
        <div className="flex flex-wrap items-center gap-cdt-3">
          <Button variant="primary" disabled>
            Primaria deshabilitada
          </Button>
          <Button variant="primary" loading>
            Insertando…
          </Button>
        </div>
      </Section>

      <Section id="icon-button" title="IconButton">
        <div className="flex flex-wrap items-center gap-cdt-3">
          <IconButton label="Buscar en el catálogo" variant="secondary">
            <FileSearch className="h-5 w-5" />
          </IconButton>
          <IconButton label="Eliminar corrida" variant="destructive">
            <Trash2 className="h-5 w-5" />
          </IconButton>
          <IconButton label="Confirmar" variant="primary" loading>
            <CheckCircle2 className="h-5 w-5" />
          </IconButton>
        </div>
      </Section>

      <Section id="badges" title="Badge — estados del contrato (nunca solo color)">
        <div className="flex flex-wrap items-center gap-cdt-3">
          <Badge status="verified" />
          <Badge status="no_evidence" />
          <Badge status="interrupted" />
          <Badge status="warning" />
          <Badge status="failed" />
        </div>
      </Section>

      <Section id="card" title="Card">
        <Card className="max-w-sm">
          <CardHeader>
            <p className="text-cdt-sm font-cdt-bold text-cdt-slate-900">Encabezado de tarjeta</p>
          </CardHeader>
          <CardBody>
            <p className="text-cdt-sm text-cdt-slate-600">
              Contenedor base sin sombra dura ni degradado: un borde de 1px y un
              radio pequeño.
            </p>
          </CardBody>
          <CardFooter>
            <Button variant="primary">Acción</Button>
            <Button variant="quiet">Cancelar</Button>
          </CardFooter>
        </Card>
      </Section>

      <Section id="disclosure" title="Disclosure">
        <Disclosure summary="Ver detalle técnico de la consulta">
          <div className="mt-cdt-2 rounded-cdt-md bg-cdt-blue-50 p-cdt-3 text-cdt-xs text-cdt-slate-600">
            <p>
              <strong className="text-cdt-slate-900">Dataset:</strong> ji8i-4anb
            </p>
            <p>
              <strong className="text-cdt-slate-900">Consulta SoQL:</strong> {REAL_SOQL}
            </p>
          </div>
        </Disclosure>
      </Section>

      <Section id="modal" title="Modal">
        <Button variant="secondary" onClick={() => setModalOpen(true)}>
          Abrir modal de ejemplo
        </Button>
        <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Confirmar inserción">
          <p className="mb-cdt-4 text-cdt-sm text-cdt-slate-600">
            Este es un modal de ejemplo de la galería: foco inicial, trampa de
            Tab/Mayús+Tab, cierre con Escape y retorno de foco al botón que lo
            abrió.
          </p>
          <div className="flex justify-end gap-cdt-2">
            <Button variant="quiet" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>
              Confirmar
            </Button>
          </div>
        </Modal>
      </Section>

      <Section id="tabs" title="Tabs">
        <Tabs
          items={[
            { id: "resumen", label: "Resumen", content: <p className="text-cdt-sm text-cdt-slate-600">Panel de resumen.</p> },
            { id: "detalle", label: "Detalle técnico", content: <p className="text-cdt-sm text-cdt-slate-600">Panel de detalle técnico.</p> },
            { id: "historial", label: "Historial", content: <p className="text-cdt-sm text-cdt-slate-600">Panel de historial.</p> },
          ]}
        />
      </Section>

      <Section id="table" title="Table">
        <Table
          caption="1 fila devuelta por datos.gov.co (corrida real e6ae9a62-…)"
          columns={[{ key: "metric_avg_1", header: "metric_avg_1" }]}
          rows={[REAL_EVIDENCE_ROW]}
        />
      </Section>

      <Section id="live-region" title="LiveRegion">
        <p className="text-cdt-sm text-cdt-slate-600">
          Región <code>aria-live=&quot;polite&quot;</code> visualmente oculta (revélala con un
          lector de pantalla). No emite eventos del agente; solo demuestra el
          patrón de anuncio agrupado.
        </p>
        <LiveRegion message="Investigación completada." />
      </Section>

      <Section id="skeleton" title="Skeleton">
        <div className="flex max-w-sm flex-col gap-cdt-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </Section>

      <Section id="visually-hidden" title="VisuallyHidden">
        <Button variant="secondary">
          Ver evidencia
          <VisuallyHidden> de la deserción escolar en Antioquia</VisuallyHidden>
        </Button>
      </Section>

      <Section id="ruta-central" title='Composición "ruta central" — muestra del sistema, no RunTimeline'>
        <p className="max-w-2xl text-cdt-sm text-cdt-slate-600">
          Esta composición ilustra el lenguaje visual aprobado en DESIGN-01
          (Variante A) usando texto y cifras reales de una sola corrida
          capturada. <strong className="text-cdt-slate-900">No es el componente `RunTimeline`</strong>
          {" "}— no hay lógica de estado, no consume SSE y los tiempos mostrados
          son estáticos, no derivados en vivo.
        </p>
        <Card className="max-w-md">
          <CardBody>
            <p className="mb-cdt-3 text-cdt-sm font-cdt-bold text-cdt-slate-900">{REAL_QUESTION}</p>
            <ol className="relative flex flex-col gap-cdt-4 border-l-2 border-cdt-blue-100 pl-cdt-4">
              {REAL_STEPS.map((step, index) => (
                <li key={`${step.node}-${index}`} className="relative">
                  <span
                    className="absolute -left-[23px] top-1 h-3 w-3 rounded-cdt-full bg-cdt-success"
                    aria-hidden="true"
                  />
                  <p className="text-cdt-sm text-cdt-slate-900">{messageForNode(step.node)}</p>
                  {step.elapsed ? (
                    <p className="text-cdt-xs text-cdt-slate-600">{step.elapsed} transcurridos</p>
                  ) : null}
                </li>
              ))}
            </ol>
            <div className="mt-cdt-4 rounded-cdt-md border border-cdt-blue-100 p-cdt-3">
              <Badge status="verified" className="mb-cdt-2" />
              <p className="break-words text-cdt-xl font-cdt-bold text-cdt-blue-900">
                {REAL_CLAIM_DISPLAY_VALUE}
              </p>
              <p className="break-words text-cdt-xs text-cdt-slate-600">
                {REAL_PUBLISHER} · {REAL_DATASET_NAME} · corte {REAL_DATA_CUTOFF}
              </p>
            </div>
          </CardBody>
        </Card>
      </Section>

      <AgentDemoSection />
    </div>
  );
}

/**
 * Gate de disponibilidad: la galería solo debe existir en desarrollo. En
 * producción, `next build` ejecuta esta función con
 * `process.env.NODE_ENV === "production"` y `notFound: true` hace que la
 * ruta se sirva como 404 real (no un simple `return null` en el cliente).
 * Lógica real en `lib/gallery/devOnlyGuard.js` (sin JSX, probada por
 * unidad ahí).
 */
export async function getStaticProps() {
  return devOnlyGetStaticProps();
}
