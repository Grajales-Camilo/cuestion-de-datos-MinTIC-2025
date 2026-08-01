import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Head from "next/head";
import { resolveBackendUrl } from "../lib/config/backendUrl";
import { useAgentRun } from "../hooks/useAgentRun";
import { useConsent } from "../hooks/useConsent";
import { useRunHistory } from "../hooks/useRunHistory";
import { usePolitePolite } from "../hooks/usePolitePolite";
import {
  QuestionComposer,
  CopilotPanel,
  IntentSummary,
  RunTimeline,
  ConnectionStatus,
  TerminalPanel,
} from "../components/agent";
import { ConsentDialog } from "../components/consent";
import { HistoryList } from "../components/history";
import { LiveRegion } from "../components/ui/LiveRegion";
import {
  DocumentSections,
  DocumentPersistenceStatus,
  ExportDocumentButton,
  TemplatePicker,
  DocumentMenuBar,
} from "../components/document";
import { createTemplateDocument } from "../lib/document/documentModel";
import { useDocumentAutosave } from "../hooks/useDocumentAutosave";
import { RUN_STATUS } from "../lib/agent/runStates";

const BUSY_STATUSES = new Set([RUN_STATUS.CREATING, RUN_STATUS.STREAMING, RUN_STATUS.RECONNECTING]);

/**
 * Resuelve `NEXT_PUBLIC_BACKEND_URL` una sola vez por montaje. Un fallo de
 * configuración se muestra como un mensaje honesto en español, nunca como
 * un fallback silencioso a `localhost` ni una pantalla en blanco (D-7,
 * `frontend/README.md`).
 */
function useBackendUrl() {
  return useMemo(() => {
    try {
      return { url: resolveBackendUrl(), error: null };
    } catch (error) {
      return { url: null, error: error.message };
    }
  }, []);
}

/**
 * `/app` — ruta funcional v2 (D-7). Se conecta EXCLUSIVA y DIRECTAMENTE al
 * backend FastAPI determinista vía `NEXT_PUBLIC_BACKEND_URL` y `/v2/*`:
 * ningún `fetch` a `/api/consultar_v2`, ningún proxy de Next, ningún
 * componente ni prompt del agente legacy. `/` permanece intacta y aislada.
 *
 * Composición de F3-7B: consentimiento versionado antes del primer `POST`
 * (D-9), historial de sesión con reejecución/refinamiento/borrado (RF-502,
 * RF-803), y el copiloto en vivo ya construido en F3-7A
 * (`useAgentRun`, `RunTimeline`, `ConnectionStatus`, `TerminalPanel`), y
 * la presentación de evidencia de F4-02 (`EvidenceCard`, ya integrada
 * dentro de `TerminalPanel`).
 *
 * F5-02 integra un documento Tiptap en memoria y la inserción segura de la
 * evidencia de F4 mediante el contrato cerrado por F5-01. F5-03A añade el
 * modelo documental versionado por secciones y "Investigar esta sección",
 * que deriva `context_hint` del texto visible de la sección y lo envía
 * junto a una pregunta escrita por el humano — sin LLM ni pregunta
 * fabricada en este incremento.
 *
 * RF-101-01 implementó el modelo/exportación de las tres plantillas
 * aprobadas por RF-101 (libre, MGA — ADR-0005, plan de desarrollo —
 * ADR-0004). RF-101-02 añade la capa visual: si al terminar la
 * restauración (F6-01) no hay documento recuperable, se muestra
 * `TemplatePicker` para que el usuario elija explícitamente una de las
 * tres; un documento restaurado nunca pasa por el selector ni se
 * reemplaza. Cambiar la plantilla de un documento ya abierto y el flujo
 * "Nuevo documento" quedan fuera de este incremento a propósito.
 */
export default function AppPage() {
  const { url: baseUrl, error: backendUrlError } = useBackendUrl();

  const consent = useConsent();

  // Bridge explícito y mínimo: `useAgentRun` no puede recibir el callback
  // de `useRunHistory` antes de que ese segundo hook exista (se construye
  // con `agentRun.start`/`agentRun.resume` inyectados), así que la
  // notificación se indirecciona por una ref que se actualiza cada
  // render — nunca se salta la frontera de `onLifecycle` ni se fusionan
  // los dos hooks en uno.
  const historyLifecycleRef = useRef(() => {});
  const stableOnLifecycle = useCallback((event) => historyLifecycleRef.current(event), []);

  const agentRun = useAgentRun({
    baseUrl: baseUrl ?? "",
    consentGranted: consent.consentGranted,
    onLifecycle: stableOnLifecycle,
  });

  const history = useRunHistory({
    baseUrl: baseUrl ?? "",
    startRun: agentRun.start,
    resumeRunTransport: agentRun.resume,
  });

  useEffect(() => {
    historyLifecycleRef.current = history.handleAgentLifecycle;
  }, [history.handleAgentLifecycle]);

  const { message: liveMessage } = usePolitePolite({ state: agentRun.state });

  const [pendingDraft, setPendingDraft] = useState(null);
  const [prefill, setPrefill] = useState(null);
  // Cerrado por defecto: en <1024px, `CopilotPanel` abierto es un `Modal` a
  // pantalla completa (`fixed inset-0`) — arrancar en `true` bloquearía el
  // composer detrás de un panel vacío antes de que exista una investigación
  // que mostrar. `handleComposerSubmit` lo abre en cuanto hay algo real.
  const [copilotOpen, setCopilotOpen] = useState(false);
  // Modelo documental versionado por secciones (F5-03A). Se mantiene
  // reactivo (no una ref) porque "Investigar esta sección" debe derivar el
  // `context_hint` del contenido REAL más reciente, no del valor inicial
  // con el que se montó cada `DocumentEditor` (que solo lee `initialContent`
  // una vez, en modo no controlado — ver `DocumentEditor.jsx`).
  //
  // Arranca en `null` a propósito (F6-01, barrera load-before-save):
  // `DocumentEditor` es no controlado, así que si `DocumentSections` se
  // montara primero con una plantilla por defecto y LUEGO se reemplazara
  // por un documento restaurado de `cdd.doc.v1`, el editor ya montado
  // seguiría mostrando el contenido viejo. `documentModel` se siembra desde
  // `autosave.restoredDocument` EXACTAMENTE UNA VEZ, cuando
  // `useDocumentAutosave` termina de decidir si hay algo que restaurar
  // (`autosave.isRestoring` pasa a `false`) — nunca se recrea, normaliza ni
  // reemplaza un documento restaurado, y no se llama `createTemplateDocument`
  // en esa rama.
  //
  // RF-101-02: si al terminar la restauración NO hay `restoredDocument`
  // (`EMPTY`/`CORRUPT`/`INVALID`/`UNAVAILABLE`/`FUTURE_VERSION`/
  // `MIGRATION_FAILED`), `documentModel` permanece en `null` a propósito —
  // ya no se crea la plantilla libre automáticamente. El JSX de abajo
  // muestra `TemplatePicker` en ese estado ("awaiting-template"); solo
  // `handleCreateDocument` (disparado por la confirmación explícita del
  // usuario) puede sacar a `documentModel` de `null` en ese caso.
  const [documentModel, setDocumentModel] = useState(null);
  const autosave = useDocumentAutosave();
  // La restauración inicial desde `localStorage` debe sembrar `documentModel`
  // como MUCHO una vez por carga de página. Sin esta guarda, "Cerrar"
  // (RF-105) volvería a traer el documento restaurado de inmediato: al
  // poner `documentModel` en `null`, este mismo efecto se re-ejecuta (está
  // en sus dependencias) y `autosave.restoredDocument` sigue siendo el
  // mismo objeto no nulo de la restauración original (ese estado nunca se
  // limpia después del montaje).
  const hasSeededDocumentRef = useRef(false);

  useEffect(() => {
    if (hasSeededDocumentRef.current) return;
    if (documentModel !== null || autosave.isRestoring) return;
    if (autosave.restoredDocument === null) return; // awaiting-template: espera selección del usuario
    hasSeededDocumentRef.current = true;
    setDocumentModel(autosave.restoredDocument);
  }, [documentModel, autosave.isRestoring, autosave.restoredDocument]);

  // Única forma de crear un documento nuevo en este incremento (RF-101-02):
  // el usuario elige y confirma una plantilla en TemplatePicker. Nunca se
  // preselecciona nada ni se llama automáticamente. El autoguardado
  // existente persiste el resultado mediante el flujo normal
  // (`notifyChange`, más abajo) — esta función nunca escribe en
  // `localStorage` directamente.
  const handleCreateDocument = useCallback((templateId) => {
    hasSeededDocumentRef.current = true;
    setDocumentModel(createTemplateDocument(templateId));
  }, []);

  // Archivo > Cerrar (RF-105): vuelve al selector de plantillas. NO borra
  // nada de `localStorage` — el documento actual sigue autoguardado tal
  // cual y reaparece si el usuario recarga la página; solo deja de
  // mostrarse en esta pestaña hasta que se elija (y confirme, ver
  // `DocumentMenuBar`) una plantilla nueva.
  const handleCloseDocument = useCallback(() => {
    setDocumentModel(null);
  }, []);

  useEffect(() => {
    if (documentModel !== null) autosave.notifyChange(documentModel);
  }, [documentModel, autosave]);

  const defaultSectionId = documentModel?.sections[0]?.sectionId ?? null;
  const [documentFeedback, setDocumentFeedback] = useState("");
  const documentSectionsRef = useRef(null);
  const exportButtonRef = useRef(null);
  const prefillNonceRef = useRef(0);

  // Ver `DocumentMenuBar.jsx`: el menú Archivo/Editar/Formato lee
  // `documentSectionsRef.current.getActiveEditor()` directamente (no está
  // en el árbol de estado de React), así que necesita un disparador propio
  // para re-renderizar cuando cambia el foco/selección/contenido de
  // CUALQUIER sección.
  const [editorActivityTick, setEditorActivityTick] = useState(0);
  const handleEditorActivity = useCallback(() => setEditorActivityTick((tick) => tick + 1), []);

  const isBusy = BUSY_STATUSES.has(agentRun.state.status);

  const handleSectionChange = useCallback((sectionId, json) => {
    setDocumentModel((previous) => ({
      ...previous,
      sections: previous.sections.map((section) =>
        section.sectionId === sectionId ? { ...section, content: json } : section
      ),
    }));
  }, []);

  // Ruta compartida por la pregunta libre (RF-104 preexistente, sección de
  // destino = la primera del documento) y por "Investigar esta sección"
  // (RF-104, F5-03A): ambas respetan el mismo gate de consentimiento
  // (RF-802/D-9). `sectionId` viaja DENTRO del borrador (nunca en un estado
  // aparte de este componente): `useAgentRun` es la única fuente de verdad
  // de la asociación runId→sectionId, vía `agentRun.state.sectionId`
  // (F5-03A-R1). Si el usuario cancela el consentimiento, `pendingDraft` se
  // descarta sin que `agentRun.start` se haya llamado nunca — no hay
  // asociación residual porque el reducer nunca llegó a fijarla.
  const startInvestigation = useCallback(
    (draft, sectionId) => {
      setDocumentFeedback("");
      setCopilotOpen(true);
      if (consent.consentGranted) {
        agentRun.start({ ...draft, sectionId });
        return;
      }
      // RF-802: la primera investigación válida abre el modal ANTES de
      // cualquier POST — `agentRun.start` solo se llama tras aceptar.
      setPendingDraft({ ...draft, sectionId });
    },
    [consent.consentGranted, agentRun]
  );

  const handleComposerSubmit = useCallback(
    (draft) => startInvestigation(draft, defaultSectionId),
    [startInvestigation, defaultSectionId]
  );

  const handleSectionInvestigate = useCallback(
    (draft, sectionId) => startInvestigation(draft, sectionId),
    [startInvestigation]
  );

  const handleManualEntryInserted = useCallback(() => {
    setDocumentFeedback("El aporte manual se agregó al documento.");
  }, []);

  // Hallazgo de revisión manual F8-02 (NVDA): `history.deleteRun` ya
  // resolvía el DELETE real y `HistoryList` ya retiraba la tarjeta de la
  // lista, pero nada anunciaba el éxito para quien usa lector de
  // pantalla — solo el error tenía `role="alert"` (`HistoryList.jsx`). El
  // fallo YA se anuncia (visible/hablado) porque la tarjeta permanece con
  // su mensaje de error; aquí solo se cubre el camino de éxito, que antes
  // era silencioso.
  const handleDeleteRun = useCallback(
    async (runId) => {
      const result = await history.deleteRun(runId);
      if (result?.ok) {
        setDocumentFeedback("La investigación se borró de forma irreversible.");
      }
      return result;
    },
    [history],
  );

  // `agentRun.start` cierra sobre el `consentGranted` de ESTE render:
  // llamarlo en el mismo tick que `consent.acceptConsent()` seguiría
  // viendo el valor anterior (`false`) porque la actualización de estado
  // de React todavía no se aplicó — el `useCallback` de `useAgentRun` no
  // se recrea con `consentGranted: true` hasta el siguiente render. Se
  // encola el borrador y un efecto lo dispara en cuanto el render con el
  // consentimiento ya concedido exista, garantizando exactamente una
  // llamada a `start` con el borrador pendiente.
  const [queuedStart, setQueuedStart] = useState(null);

  const handleAcceptConsent = useCallback(
    ({ contextHint }) => {
      const draft = pendingDraft;
      consent.acceptConsent();
      setPendingDraft(null);
      if (draft) {
        setQueuedStart({ question: draft.question, contextHint, sectionId: draft.sectionId ?? null });
      }
    },
    [consent, pendingDraft]
  );

  useEffect(() => {
    if (queuedStart && consent.consentGranted) {
      agentRun.start(queuedStart);
      setQueuedStart(null);
    }
  }, [queuedStart, consent.consentGranted, agentRun]);

  const handleCancelConsent = useCallback(() => {
    setPendingDraft(null);
  }, []);

  const handleRefine = useCallback(
    (runId) => {
      const draft = history.refine(runId);
      if (!draft) return;
      prefillNonceRef.current += 1;
      setPrefill({ ...draft, nonce: prefillNonceRef.current });
    },
    [history]
  );

  const handleRetryConnection = useCallback(() => {
    if (!agentRun.state.runId) return;
    history.resumeRun(agentRun.state.runId);
  }, [agentRun.state.runId, history]);

  const handleReformulate = useCallback(() => {
    setCopilotOpen(false);
  }, []);

  // La sección de destino viene de `agentRun.state.sectionId` — la corrida
  // ACTUALMENTE presentada, nunca un valor global de este componente que
  // pudiera arrastrar la sección de una corrida anterior (F5-03A-R1: única
  // fuente de verdad, ver `useAgentRun.js`). Si esa sección ya no está
  // montada, `insertEvidenceCitation` de `DocumentSections` devuelve
  // `false` y aquí se falla cerrado: nunca se reintenta en otra sección.
  const handleInsertEvidence = useCallback(
    (payload) => {
      const sectionId = agentRun.state.sectionId;
      try {
        const inserted = sectionId
          ? documentSectionsRef.current?.insertEvidenceCitation(sectionId, payload) ?? false
          : false;
        if (!inserted) {
          setDocumentFeedback("No pudimos insertar la evidencia. El documento no cambió.");
          return false;
        }

        const updatedJson = documentSectionsRef.current.getSectionJSON(sectionId);
        if (updatedJson) handleSectionChange(sectionId, updatedJson);
        setDocumentFeedback("La evidencia se insertó en el documento.");

        const isMobile =
          typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches;
        if (isMobile) setCopilotOpen(false);
        window.requestAnimationFrame(() => documentSectionsRef.current?.focusSection(sectionId));
        return true;
      } catch {
        setDocumentFeedback("No pudimos insertar la evidencia. El documento no cambió.");
        return false;
      }
    },
    [agentRun.state.sectionId, handleSectionChange]
  );

  const handleAddManualSource = useCallback(
    (source) => {
      const sectionId = agentRun.state.sectionId;
      const opened = sectionId
        ? documentSectionsRef.current?.openManualEntry(sectionId, source) ?? false
        : false;
      if (!opened) {
        setDocumentFeedback(
          "Usa “Agregar dato manual” en la sección donde quieres incorporar el aporte.",
        );
        return false;
      }

      const isMobile =
        typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches;
      if (isMobile) setCopilotOpen(false);
      return true;
    },
    [agentRun.state.sectionId],
  );

  const liveRegionMessage = documentFeedback || liveMessage;

  useEffect(() => {
    if (!documentFeedback) return undefined;
    const timeoutId = window.setTimeout(() => setDocumentFeedback(""), 4_000);
    return () => window.clearTimeout(timeoutId);
  }, [documentFeedback]);

  return (
    <div className="cdt-v2 flex min-h-screen flex-col bg-cdt-white">
      <Head>
        <title>Cuestión de Datos — Investigación</title>
      </Head>

      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-cdt-4 focus:top-cdt-4 focus:z-50 focus:rounded-cdt-md focus:bg-cdt-blue-900 focus:px-cdt-4 focus:py-cdt-2 focus:text-cdt-white"
      >
        Saltar al contenido
      </a>

      <header className="border-b border-cdt-blue-100 bg-cdt-blue-50 px-cdt-4 py-cdt-3">
        <h1 className="text-cdt-lg font-cdt-bold text-cdt-blue-900">Cuestión de Datos</h1>
      </header>

      <LiveRegion message={liveRegionMessage} />

      {backendUrlError ? (
        <main id="contenido" tabIndex={-1} className="p-cdt-6">
          <p role="alert" className="text-cdt-sm text-cdt-error">
            No se pudo conectar con el servicio: {backendUrlError}
          </p>
        </main>
      ) : documentModel === null ? (
        // `autosave.isRestoring`: restauración de F6-01 aún en curso —
        // `DocumentSections` NI `TemplatePicker` se montan todavía (ver el
        // comentario junto a `useState(null)` más arriba). Una vez termina
        // la restauración sin `restoredDocument` (RF-101-02:
        // "awaiting-template"), se añade `TemplatePicker` bajo el mismo
        // `DocumentPersistenceStatus` que ya muestra el aviso de
        // corrupción/versión futura/migración fallida que corresponda —
        // nunca se reemplaza ese aviso, ambos conviven.
        <main id="contenido" tabIndex={-1} className="p-cdt-6">
          <DocumentPersistenceStatus
            status={autosave.status}
            error={autosave.error}
            notice={autosave.notice}
            blockedEnvelope={autosave.blockedEnvelope}
            currentDocument={documentModel}
            onDismissNotice={autosave.dismissNotice}
          />
          {!autosave.isRestoring ? (
            <div className="mt-cdt-6">
              <TemplatePicker onCreateDocument={handleCreateDocument} />
            </div>
          ) : null}
        </main>
      ) : (
        <main
          id="contenido"
          tabIndex={-1}
          className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-cdt-6 p-cdt-4 lg:flex-row lg:items-start"
        >
          <div className="flex min-w-0 flex-1 flex-col gap-cdt-8">
            <div className="rounded-cdt-lg border border-cdt-blue-100 bg-cdt-blue-50">
              <DocumentMenuBar
                documentModel={documentModel}
                documentSectionsRef={documentSectionsRef}
                editorActivityTick={editorActivityTick}
                exportButtonRef={exportButtonRef}
                onCreateDocument={handleCreateDocument}
                onCloseDocument={handleCloseDocument}
                onFeedback={setDocumentFeedback}
              />
            </div>

            <div className="flex flex-wrap items-start justify-between gap-cdt-3">
              <DocumentPersistenceStatus
                status={autosave.status}
                error={autosave.error}
                notice={autosave.notice}
                blockedEnvelope={autosave.blockedEnvelope}
                currentDocument={documentModel}
                onDismissNotice={autosave.dismissNotice}
              />
              <ExportDocumentButton ref={exportButtonRef} documentModel={documentModel} />
            </div>

            <DocumentSections
              ref={documentSectionsRef}
              document={documentModel}
              onSectionChange={handleSectionChange}
              onInvestigateSection={handleSectionInvestigate}
              onManualEntryInserted={handleManualEntryInserted}
              onEditorActivity={handleEditorActivity}
              disabled={isBusy}
            />

            <section aria-labelledby="composer-heading" className="flex flex-col gap-cdt-3">
              <h2 id="composer-heading" className="text-cdt-base font-cdt-bold text-cdt-slate-900">
                Nueva investigación
              </h2>
              <QuestionComposer
                onSubmit={handleComposerSubmit}
                consentGranted
                disabled={isBusy}
                prefill={prefill}
              />
            </section>

            <section aria-labelledby="history-heading" className="flex flex-col gap-cdt-3">
              <div className="flex flex-wrap items-center justify-between gap-cdt-2">
                <h2 id="history-heading" className="text-cdt-base font-cdt-bold text-cdt-slate-900">
                  Historial de esta sesión
                </h2>
                <label className="flex items-center gap-cdt-2 text-cdt-xs text-cdt-slate-600">
                  <input
                    type="checkbox"
                    checked={history.rememberRuns}
                    onChange={(event) => history.setRememberRuns(event.target.checked)}
                    className="h-4 w-4"
                  />
                  Recordar mis investigaciones en este equipo
                </label>
              </div>
              <HistoryList
                runs={history.runs}
                onRerun={history.rerun}
                onRefine={handleRefine}
                onDelete={handleDeleteRun}
                onResume={history.resumeRun}
                isDeletingRun={history.isDeletingRun}
              />
            </section>
          </div>

          <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} title="Investigación en curso">
            <div className="flex flex-col gap-cdt-4">
              <IntentSummary intention={agentRun.state.intention} onReformulate={handleReformulate} />
              <ConnectionStatus
                status={agentRun.state.status}
                reconnectAttempt={agentRun.state.reconnect.attempts}
                onRetry={handleRetryConnection}
              />
              <RunTimeline steps={agentRun.state.steps} status={agentRun.state.status} />
              <TerminalPanel
                state={agentRun.state}
                onRestart={agentRun.reset}
                onInsertEvidence={handleInsertEvidence}
                onAddManualSource={handleAddManualSource}
              />
            </div>
          </CopilotPanel>
        </main>
      )}

      <ConsentDialog
        open={pendingDraft !== null}
        draft={pendingDraft}
        rememberRuns={history.rememberRuns}
        onRememberRunsChange={history.setRememberRuns}
        onAccept={handleAcceptConsent}
        onCancel={handleCancelConsent}
      />
    </div>
  );
}
