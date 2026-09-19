import type { components } from "../api/schema";

type Provenance = components["schemas"]["Provenance"];

const STYLES: Record<Provenance, string> = {
  LIVE: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  SIMULATED: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  FIXTURE: "bg-slate-500/15 text-slate-300 border-slate-500/40",
};

/**
 * docs/18: every event/effect renders its own provenance -- never one
 * global "Live" badge for the whole page.
 */
export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STYLES[provenance]}`}
    >
      {provenance}
    </span>
  );
}
