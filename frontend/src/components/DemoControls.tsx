import { useEffect, useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";

type Appointment = components["schemas"]["Appointment"];
type DemoSeedRefs = components["schemas"]["DemoSeedRefs"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      <div className="mt-2 space-y-2">{children}</div>
    </div>
  );
}

const inputCls =
  "w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600";
const buttonCls = "rounded bg-sky-600 px-3 py-1 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50";

export function DemoControls({
  creds,
  selectedCaseId,
  appointments,
  onCaseCreated,
  onMutated,
}: {
  creds: OperatorCredentials;
  selectedCaseId: string | null;
  appointments: Appointment[];
  onCaseCreated: (caseId: string) => void;
  onMutated: () => void;
}) {
  const client = createApiClient(creds);
  const [refs, setRefs] = useState<DemoSeedRefs | null>(null);

  useEffect(() => {
    client.GET("/api/v1/demo/seed-refs").then(({ data }) => data && setRefs(data));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [description, setDescription] = useState("Water stain spreading across the rear bedroom ceiling.");
  const [location, setLocation] = useState("Rear bedroom ceiling");
  const [simulateHazard, setSimulateHazard] = useState(false);
  const [creatingCase, setCreatingCase] = useState(false);

  async function createCase() {
    if (!refs) return;
    setCreatingCase(true);
    try {
      const { data } = await client.POST("/api/v1/demo/intake", {
        body: {
          property_id: refs.property_id,
          tenant_id: refs.tenant_id,
          description,
          location,
          source_text: description,
          // All-NO is the safe hero path; leaving gas UNKNOWN exercises the
          // deterministic hazard gate that must escalate before any model call.
          safety_answers: {
            gas: simulateHazard ? "UNKNOWN" : "NO",
            fire: "NO",
            water_near_electrics: "NO",
            structural_danger: "NO",
            uncontrolled_flood: "NO",
            vulnerability_concern: "NO",
          },
        },
      });
      if (data) onCaseCreated(data.case_id);
    } finally {
      setCreatingCase(false);
    }
  }

  const [reportAppointmentId, setReportAppointmentId] = useState("");
  const [reportText, setReportText] = useState("Tiles are beyond safe ladder reach; scaffold platform needed.");
  const [submittingReport, setSubmittingReport] = useState(false);

  async function submitReport() {
    if (!selectedCaseId || !reportAppointmentId) return;
    setSubmittingReport(true);
    try {
      await client.POST("/api/v1/demo/cases/{case_id}/observations", {
        params: { path: { case_id: selectedCaseId } },
        body: { kind: "CONTRACTOR_REPORT", appointment_id: reportAppointmentId, text: reportText, observed_at: new Date().toISOString() },
      });
      onMutated();
    } finally {
      setSubmittingReport(false);
    }
  }

  const [feedbackText, setFeedbackText] = useState("Yes, the roof looks fixed and there's no more staining.");
  const [confirmsResolved, setConfirmsResolved] = useState(true);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  async function submitFeedback() {
    if (!selectedCaseId) return;
    setSubmittingFeedback(true);
    try {
      await client.POST("/api/v1/demo/cases/{case_id}/observations", {
        params: { path: { case_id: selectedCaseId } },
        body: { kind: "TENANT_FEEDBACK", confirms_resolved: confirmsResolved, text: feedbackText },
      });
      onMutated();
    } finally {
      setSubmittingFeedback(false);
    }
  }

  const [windowAppointmentId, setWindowAppointmentId] = useState("");

  async function submitWindowEnded() {
    if (!selectedCaseId || !windowAppointmentId) return;
    await client.POST("/api/v1/demo/cases/{case_id}/observations", {
      params: { path: { case_id: selectedCaseId } },
      body: { kind: "ATTENDANCE_WINDOW_ENDED", appointment_id: windowAppointmentId },
    });
    onMutated();
  }

  const [resetArmed, setResetArmed] = useState(false);

  async function resetDemo() {
    if (!resetArmed) {
      setResetArmed(true);
      setTimeout(() => setResetArmed(false), 4000);
      return;
    }
    await client.POST("/api/v1/demo/reset", { params: { query: { confirm_reset: true } } });
    setResetArmed(false);
    onMutated();
  }

  return (
    <div className="space-y-3">
      <Section title="New demo case">
        <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
        <input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={simulateHazard} onChange={(e) => setSimulateHazard(e.target.checked)} />
          Simulate hazard (unknown gas safety — triggers the safety gate)
        </label>
        <button type="button" className={buttonCls} disabled={creatingCase || !refs} onClick={createCase}>
          {creatingCase ? "Creating…" : "Start intake"}
        </button>
      </Section>

      <Section title="Simulate contractor report">
        <select className={inputCls} value={reportAppointmentId} onChange={(e) => setReportAppointmentId(e.target.value)}>
          <option value="">Select appointment…</option>
          {appointments.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id.slice(0, 8)} · attempt {a.attempt_number} · {a.status}
            </option>
          ))}
        </select>
        <textarea className={inputCls} rows={2} value={reportText} onChange={(e) => setReportText(e.target.value)} />
        <button type="button" className={buttonCls} disabled={submittingReport || !reportAppointmentId} onClick={submitReport}>
          {submittingReport ? "Submitting…" : "Submit report"}
        </button>
      </Section>

      <Section title="Simulate tenant feedback">
        <textarea className={inputCls} rows={2} value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)} />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={confirmsResolved} onChange={(e) => setConfirmsResolved(e.target.checked)} />
          Tenant confirms resolved
        </label>
        <button type="button" className={buttonCls} disabled={submittingFeedback || !selectedCaseId} onClick={submitFeedback}>
          {submittingFeedback ? "Submitting…" : "Submit feedback"}
        </button>
      </Section>

      <Section title="Simulate attendance window ended">
        <select className={inputCls} value={windowAppointmentId} onChange={(e) => setWindowAppointmentId(e.target.value)}>
          <option value="">Select appointment…</option>
          {appointments.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id.slice(0, 8)} · attempt {a.attempt_number} · {a.status}
            </option>
          ))}
        </select>
        <button type="button" className={buttonCls} disabled={!windowAppointmentId} onClick={submitWindowEnded}>
          Mark window ended
        </button>
      </Section>

      <Section title="Reset demo data">
        <p className="text-[11px] text-slate-500">Clears all non-LIVE cases. Preserves any real recorded call.</p>
        <button
          type="button"
          onClick={resetDemo}
          className={`rounded px-3 py-1 text-xs font-semibold text-white ${resetArmed ? "bg-rose-600 hover:bg-rose-500" : "bg-slate-700 hover:bg-slate-600"}`}
        >
          {resetArmed ? "Click again to confirm reset" : "Reset demo data"}
        </button>
      </Section>
    </div>
  );
}
