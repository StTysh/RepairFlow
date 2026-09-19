import { useCallback, useState } from "react";
import { CaseHeader } from "./components/CaseHeader";
import { CaseList } from "./components/CaseList";
import { DecisionCard } from "./components/DecisionCard";
import { DemoControls } from "./components/DemoControls";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { LoginGate } from "./components/LoginGate";
import { ResearchDrawer } from "./components/ResearchDrawer";
import { Timeline } from "./components/Timeline";
import { VoicePanel } from "./components/VoicePanel";
import { WorkGraph } from "./components/WorkGraph";
import type { OperatorCredentials } from "./api/client";
import { useCaseDetail } from "./hooks/useCaseDetail";
import { useCaseList } from "./hooks/useCaseList";
import { useReadiness } from "./hooks/useReadiness";

function CaseWorkspace({ creds }: { creds: OperatorCredentials }) {
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const { items } = useCaseList(creds);
  const { snapshot, error: detailError } = useCaseDetail(creds, selectedCaseId);
  const readiness = useReadiness(creds);
  const [refreshTick, setRefreshTick] = useState(0);

  const handleMutated = useCallback(() => setRefreshTick((t) => t + 1), []);
  void refreshTick; // polling hooks already refresh on their own interval; this just gives buttons a visible no-op hook point

  return (
    <div className="grid h-full grid-cols-[240px_1fr_320px] overflow-hidden">
      <aside className="overflow-y-auto border-r border-slate-800 bg-slate-900/40">
        <div className="border-b border-slate-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-200">RepairFlow</h2>
          <p className="text-[11px] text-slate-500">Repair case coordinator</p>
        </div>
        <CaseList items={items} selectedCaseId={selectedCaseId} onSelect={setSelectedCaseId} />
      </aside>

      <main className="overflow-y-auto">
        {!snapshot ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            {selectedCaseId ? "Loading case…" : "Select a case, or start one from demo controls."}
          </div>
        ) : (
          <>
            <CaseHeader snapshot={snapshot} />
            <div className="space-y-4 p-6">
              {detailError && <p className="text-xs text-rose-400">{detailError}</p>}
              <WorkGraph snapshot={snapshot} />
              <DecisionCard snapshot={snapshot} creds={creds} onDecided={handleMutated} />
              <EvidenceDrawer reports={snapshot.latest_reports} communications={snapshot.communications} creds={creds} />
              <ResearchDrawer events={snapshot.recent_events} creds={creds} tavilyLive={readiness?.tavily_live ?? false} />
              <VoicePanel elevenlabsLive={readiness?.elevenlabs_live ?? false} />
              <Timeline events={snapshot.recent_events} creds={creds} caseId={snapshot.case.id} />
            </div>
          </>
        )}
      </main>

      <aside className="overflow-y-auto border-l border-slate-800 bg-slate-900/40 p-3">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Demo controls</h2>
        <DemoControls
          creds={creds}
          selectedCaseId={selectedCaseId}
          appointments={snapshot?.appointments ?? []}
          onCaseCreated={setSelectedCaseId}
          onMutated={handleMutated}
        />
      </aside>
    </div>
  );
}

function App() {
  return (
    <div className="h-screen bg-slate-950">
      <LoginGate>{(creds) => <CaseWorkspace creds={creds} />}</LoginGate>
    </div>
  );
}

export default App;
