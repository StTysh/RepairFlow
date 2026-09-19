import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  Copy,
  FileQuestion,
  Loader2,
  Mail,
  MapPin,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Phone,
  PhoneCall,
  PoundSterling,
  Share2,
} from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill, StatusBadge, UrgencyBadge } from "@/components/fixi/Badge";
import { CaseLifecycleActions } from "@/components/fixi/CaseLifecycleActions";
import { authHeader, BASE_URL } from "@/api/client";
import { useCaseDetail } from "@/hooks/use-case-detail";
import { useCaseEvents } from "@/hooks/use-case-events";
import { useCancelAppointment } from "@/hooks/use-case-actions";
import { usePropertyHistory } from "@/hooks/use-property-history";
import { useAuthedCreds } from "@/lib/auth-context";
import type { Appointment, CaseSnapshot, Communication, WorkOrder } from "@/api/types";
import { statusTone } from "@/lib/fixi-data";
import { formatDateRange, formatPence, formatRelative, initials, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// "property"/"files"/"costs" used to be a second, dead button row above
// this one ("Overview/Property/Files/Costs" with no onClick at all) --
// folded into this single functional tab set instead of leaving two rows
// where only one worked. "Overview" (the null/undefined section) keeps its
// old "All" behaviour: summary + timeline + calls together.
const sections = ["summary", "timeline", "calls", "property", "files", "costs"] as const;
type Section = (typeof sections)[number];

export const Route = createFileRoute("/maintenance/tickets/$ticketId/{-$section}")({
  loader: ({ params }) => {
    if (params.section && !sections.includes(params.section as Section)) throw notFound();
    return { section: (params.section as Section | undefined) ?? null };
  },
  head: ({ params, loaderData }) => {
    const title = `#${params.ticketId} — Fixi${loaderData?.section ? ` · ${cap(loaderData.section)}` : ""}`;
    return {
      meta: [
        { title },
        {
          name: "description",
          content:
            "Case details: property, tenant, contractor, next appointment and agent timeline.",
        },
        { property: "og:title", content: title },
      ],
    };
  },
  component: CasePage,
});

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function CasePage() {
  const { ticketId } = Route.useParams();
  const { section } = Route.useLoaderData();
  const show = (s: Section) => section === null || section === s;

  const detail = useCaseDetail(ticketId);

  if (detail.isLoading) {
    return (
      <AppShell>
        <div className="px-8 py-6 text-sm text-muted-foreground">Loading ticket…</div>
      </AppShell>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <AppShell>
        <div className="px-8 py-6">
          <Link
            to="/maintenance"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Back to tickets
          </Link>
          <p className="mt-6 text-sm text-destructive">
            Could not load this ticket. It may not exist, or the backend may be unreachable.
          </p>
        </div>
      </AppShell>
    );
  }

  const snapshot = detail.data.snapshot;
  const c = snapshot.case;
  const address = `${snapshot.property.address_line}, ${snapshot.property.postcode}`;

  return (
    <AppShell>
      <div className="px-8 py-6">
        <div className="flex items-center justify-between">
          <Link
            to="/maintenance"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Back to tickets
          </Link>
          <div className="flex items-center gap-2">
            <ToolbarButton icon={Share2}>Share</ToolbarButton>
            <ToolbarButton icon={Pencil}>Edit</ToolbarButton>
            <button className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-4 flex items-start justify-between gap-6">
          <div>
            <UrgencyBadge urgency={c.risk.urgency} />
            <h1
              className="mt-2 line-clamp-2 max-w-2xl text-2xl font-bold tracking-tight"
              title={c.title}
            >
              #{c.case_number} – {c.title}
            </h1>
            <div className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" /> {address}
              <button
                type="button"
                onClick={() => void navigator.clipboard.writeText(address)}
                title="Copy address"
              >
                <Copy className="ml-1 h-3.5 w-3.5 cursor-pointer hover:text-foreground" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {snapshot.agent_active && (
              <span className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-muted-foreground shadow-card">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Agent thinking…
              </span>
            )}
            <StatusBadge status={c.status} className="h-9 px-3.5 text-sm" />
            <CaseLifecycleActions caseId={c.id} status={c.status} version={c.version} />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-1.5">
          <SectionLink ticketId={ticketId} section={undefined} active={section === null}>
            Overview
          </SectionLink>
          <SectionLink ticketId={ticketId} section="summary" active={section === "summary"}>
            Summary
          </SectionLink>
          <SectionLink ticketId={ticketId} section="timeline" active={section === "timeline"}>
            Timeline
          </SectionLink>
          <SectionLink ticketId={ticketId} section="calls" active={section === "calls"}>
            Calls
          </SectionLink>
          <SectionLink ticketId={ticketId} section="property" active={section === "property"}>
            Property
          </SectionLink>
          <SectionLink ticketId={ticketId} section="files" active={section === "files"}>
            Files
          </SectionLink>
          <SectionLink ticketId={ticketId} section="costs" active={section === "costs"}>
            Costs
          </SectionLink>
        </div>

        <div
          className={cn("mt-3 grid gap-4", section === null ? "xl:grid-cols-2" : "xl:grid-cols-1")}
        >
          {show("summary") && <SummaryColumn snapshot={snapshot} />}
          {show("timeline") && <TimelineColumn caseId={c.id} agentActive={snapshot.agent_active} />}
          {show("calls") && <CallsColumn communications={snapshot.communications} />}
          {section === "property" && <PropertyColumn snapshot={snapshot} />}
          {section === "files" && <FilesColumn />}
          {section === "costs" && <CostsColumn workOrders={snapshot.work_orders} />}
        </div>
      </div>
    </AppShell>
  );
}

const purposeLabel: Record<Communication["purpose"], string> = {
  INTAKE: "Resident — initial report",
  AVAILABILITY: "Resident — availability",
  FOLLOW_UP: "Resident — confirmation",
  CONTRACTOR: "Contractor / worker",
};

const outcomeTone: Record<string, "green" | "amber" | "red" | "gray"> = {
  ANSWERED: "green",
  NO_ANSWER: "amber",
  VOICEMAIL: "amber",
  FAILED: "red",
  UNKNOWN: "gray",
};

function CallsColumn({ communications }: { communications: Communication[] }) {
  const calls = [...communications].sort((a, b) => {
    const at = a.started_at ?? a.ended_at ?? "";
    const bt = b.started_at ?? b.ended_at ?? "";
    return bt.localeCompare(at);
  });

  return (
    <Card className="p-5">
      <SectionHeader
        title="Calls"
        subtitle="Who was contacted, what was said, and the recording — real ElevenLabs calls, not a summary standing in for them."
      />
      {calls.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">No calls on this ticket yet.</p>
      )}
      <ul className="mt-4 space-y-3">
        {calls.map((comm) => (
          <CallRow key={comm.id} comm={comm} />
        ))}
      </ul>
    </Card>
  );
}

function CallRow({ comm }: { comm: Communication }) {
  const [open, setOpen] = useState(false);
  // direction=BROWSER + no transcript is not a phone call at all -- it's
  // the agent asking the operator (not the tenant) to do something, which
  // never gets a transcript/recording. Rendering it as "Call in progress"
  // was misleading: it looked like a stuck call that would never resolve.
  const isOperatorNote = comm.direction === "BROWSER" && comm.transcript.length === 0;
  const label = isOperatorNote ? "Needs your input" : (purposeLabel[comm.purpose] ?? comm.purpose);
  const summary =
    comm.outcome?.transcript_summary ??
    (isOperatorNote
      ? "The agent couldn't complete this automatically and is waiting on you."
      : comm.state === "ACTIVE" || comm.state === "REQUESTED"
        ? "Call in progress…"
        : comm.transcript.length > 0
          ? "No AI-generated summary for this call yet — see the full transcript below."
          : "No transcript yet.");

  return (
    <li className="rounded-lg border border-border p-3">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent">
            <PhoneCall className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              {label}
              {comm.outcome && (
                <Pill tone={outcomeTone[comm.outcome.outcome] ?? "gray"}>
                  {comm.outcome.outcome}
                </Pill>
              )}
              <Pill tone={comm.provenance === "LIVE" ? "blue" : "gray"}>{comm.provenance}</Pill>
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{summary}</p>
          </div>
        </div>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {comm.started_at ? formatRelative(comm.started_at) : ""}
        </span>
      </button>
      {open && (
        <div className="mt-3 border-t border-border pt-3">
          {isOperatorNote ? (
            <p className="text-xs text-muted-foreground">
              Not a call — no recording or transcript applies here.
            </p>
          ) : comm.recording.status === "AVAILABLE" ? (
            <RecordingPlayer communicationId={comm.id} />
          ) : (
            <p className="text-xs text-muted-foreground">
              Recording: {comm.recording.status.toLowerCase()}
            </p>
          )}
          {!isOperatorNote &&
            (comm.transcript.length > 0 ? (
              <ol className="mt-3 space-y-2">
                {comm.transcript.map((turn) => (
                  <li key={turn.turn_id} className="text-xs">
                    <span className="font-semibold">
                      {turn.speaker === "AGENT"
                        ? "Ava (AI): "
                        : turn.speaker === "USER"
                          ? "Caller: "
                          : `${turn.speaker}: `}
                    </span>
                    <span className="text-muted-foreground">{turn.text}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">No transcript recorded.</p>
            ))}
        </div>
      )}
    </li>
  );
}

function RecordingPlayer({ communicationId }: { communicationId: string }) {
  const creds = useAuthedCreds();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/communications/${communicationId}/recording`, {
        headers: { Authorization: authHeader(creds) },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      setObjectUrl(URL.createObjectURL(blob));
    } catch {
      setError("Could not load recording.");
    } finally {
      setLoading(false);
    }
  }

  if (objectUrl) return <audio controls src={objectUrl} className="h-8 w-full" />;
  return (
    <button
      type="button"
      onClick={() => void load()}
      disabled={loading}
      className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
    >
      {loading ? "Loading…" : (error ?? "▶ Play recording")}
    </button>
  );
}

function ToolbarButton({
  icon: Icon,
  children,
}: {
  icon: typeof Share2;
  children: React.ReactNode;
}) {
  return (
    <button className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-sm font-medium shadow-card hover:bg-accent">
      <Icon className="h-3.5 w-3.5" /> {children}
    </button>
  );
}

function SectionLink({
  ticketId,
  section,
  active,
  children,
}: {
  ticketId: string;
  section?: Section | undefined;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      to="/maintenance/tickets/$ticketId/{-$section}"
      params={{ ticketId, section }}
      className={cn(
        "h-8 rounded-lg border px-3 text-xs font-medium leading-8 transition-colors",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-card text-foreground hover:bg-accent",
      )}
    >
      {children}
    </Link>
  );
}

function StepDot({ tone }: { tone: "done" | "muted" }) {
  if (tone === "done")
    return (
      <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-timeline-done text-primary-foreground">
        <Check className="h-3 w-3" strokeWidth={3} />
      </span>
    );
  return (
    <span className="relative z-10 h-5 w-5 shrink-0 rounded-full border-2 border-timeline-future bg-card" />
  );
}

function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[13px] font-semibold">{children}</div>;
}

function Avatar({ initials: text, tone }: { initials: string; tone: "gray" | "green" | "purple" }) {
  const cls = {
    gray: "bg-status-gray text-status-gray-foreground",
    green: "bg-status-green text-status-green-foreground",
    purple: "bg-status-purple text-status-purple-foreground",
  }[tone];
  return (
    <div
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
        cls,
      )}
    >
      {text}
    </div>
  );
}

function IconButton({ icon: Icon }: { icon: typeof Phone }) {
  return (
    <button className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground">
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}

function NextAppointmentRow({
  appointment,
  onReschedule,
  rescheduling,
}: {
  appointment: Appointment;
  onReschedule: () => void;
  rescheduling: boolean;
}) {
  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);
  return (
    <div className="mt-2 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
          <Calendar className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-medium">{date}</div>
          <div className="text-xs text-muted-foreground">{time}</div>
        </div>
      </div>
      <OutlineButton onClick={onReschedule} disabled={rescheduling}>
        Reschedule
      </OutlineButton>
    </div>
  );
}

function OutlineButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="h-8 rounded-lg border border-border bg-card px-3 text-xs font-medium shadow-card hover:bg-accent disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function SummaryColumn({ snapshot }: { snapshot: CaseSnapshot }) {
  const { case: c, issue, tenant, assigned_contractor, next_appointment, property } = snapshot;
  const propertyHistory = usePropertyHistory(property.id);
  const cancelAppointment = useCancelAppointment(c.id);

  async function handleReschedule() {
    if (!next_appointment) return;
    const reason = window.prompt("Reason for rescheduling this visit?") ?? "";
    try {
      await cancelAppointment.mutateAsync({ appointmentId: next_appointment.id, reason });
    } catch {
      // handled by onError toast (see use-case-actions.ts)
    }
  }

  return (
    <Card className="p-5">
      <SectionHeader title="Case overview" />
      <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{issue.description}</p>
      {c.last_decision_summary && (
        <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-[13px] leading-relaxed text-muted-foreground">
          {c.last_decision_summary}
        </p>
      )}

      <div className="mt-5 border-t border-border pt-4">
        <Label>Tenant</Label>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar initials={initials(tenant.display_name)} tone="gray" />
            <div className="leading-tight">
              <div className="text-[13px] font-medium">{tenant.display_name}</div>
              <div className="text-xs text-muted-foreground">
                {tenant.phone_e164 ?? tenant.email ?? "No contact on file"}
              </div>
            </div>
          </div>
          <div className="flex gap-1.5">
            <IconButton icon={MessageSquare} />
            <IconButton icon={Mail} />
            <IconButton icon={Phone} />
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Assigned contractor</Label>
        {assigned_contractor ? (
          <div className="mt-2 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Avatar initials={initials(assigned_contractor.display_name)} tone="green" />
              <div className="leading-tight">
                <div className="text-[13px] font-medium">{assigned_contractor.display_name}</div>
                <div className="text-xs text-muted-foreground">
                  {assigned_contractor.trade ?? "—"}
                </div>
                {assigned_contractor.phone && (
                  <div className="text-xs text-muted-foreground">{assigned_contractor.phone}</div>
                )}
              </div>
            </div>
            <OutlineButton>View profile</OutlineButton>
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">No contractor assigned yet.</p>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Next appointment</Label>
        {next_appointment ? (
          <NextAppointmentRow
            appointment={next_appointment}
            onReschedule={() => void handleReschedule()}
            rescheduling={cancelAppointment.isPending}
          />
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">No appointment scheduled yet.</p>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Property history</Label>
        {propertyHistory.isLoading && (
          <p className="mt-2 text-xs text-muted-foreground">Loading…</p>
        )}
        {propertyHistory.data && (
          <ul className="mt-2 divide-y divide-border rounded-lg border border-border">
            {propertyHistory.data.items.slice(0, 4).map((h) => (
              <li
                key={h.case_id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-xs"
              >
                <span className="w-16 shrink-0 text-muted-foreground">
                  {formatRelative(h.created_at)}
                </span>
                <span className="flex-1 truncate font-medium">{h.title}</span>
                <Pill tone={statusTone(h.status)}>{h.status}</Pill>
              </li>
            ))}
            {propertyHistory.data.items.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted-foreground">
                No other cases at this property.
              </li>
            )}
          </ul>
        )}
        <Link
          to="/properties/$propertyId/history"
          params={{ propertyId: property.id }}
          search={{ address: property.address_line, postcode: property.postcode }}
          className="mt-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-card text-xs font-medium shadow-card hover:bg-accent"
        >
          View full property history <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </Card>
  );
}

function TimelineColumn({ caseId, agentActive }: { caseId: string; agentActive: boolean }) {
  const events = useCaseEvents(caseId);
  const items = events.data?.items ?? [];

  return (
    <Card className="p-5">
      <SectionHeader
        title="Agent timeline"
        subtitle="What the AI agent has done and what's next."
        action={
          agentActive ? (
            <span
              className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground"
              title="The coordinator is actively working on this case right now"
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Thinking…
            </span>
          ) : undefined
        }
      />
      {events.isLoading && <p className="mt-4 text-xs text-muted-foreground">Loading…</p>}
      {events.isError && (
        <p className="mt-4 text-xs text-destructive">Could not load the timeline.</p>
      )}
      {!events.isLoading && items.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">No events recorded yet.</p>
      )}
      <ol className="mt-4">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li
              key={item.id}
              className="relative flex animate-in gap-3 pb-5 fade-in slide-in-from-top-1 duration-300 last:pb-0"
            >
              {!last && (
                <span className="absolute left-[9px] top-5 h-full w-0.5 bg-timeline-done" />
              )}
              <StepDot tone="done" />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-[13px] font-semibold">{item.display_title}</div>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {formatRelative(item.occurred_at)}
                  </span>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {item.display_description}
                </p>
              </div>
            </li>
          );
        })}
        {agentActive && (
          <li className="relative flex animate-in gap-3 fade-in duration-300">
            <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-timeline-future bg-card">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="text-[13px] font-semibold text-muted-foreground">
                Deciding next step…
              </div>
            </div>
          </li>
        )}
      </ol>
    </Card>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-[13px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

const roofResponsibilityLabel: Record<string, string> = {
  LANDLORD: "Landlord",
  OTHER: "Other",
  UNKNOWN: "Unknown",
};

/** Real property + tenant data already fetched as part of the case
 * snapshot (snapshot.property / snapshot.tenant) -- this tab was dead
 * before; every field here is a real render target, not mock data. */
function PropertyColumn({ snapshot }: { snapshot: CaseSnapshot }) {
  const { property, tenant } = snapshot;
  return (
    <Card className="p-5">
      <SectionHeader title="Property" />
      <div className="mt-2 divide-y divide-border">
        <DetailRow label="Address" value={property.address_line} />
        <DetailRow label="Postcode" value={property.postcode} />
        <DetailRow label="Landlord reference" value={property.landlord_reference || "—"} />
        <DetailRow
          label="Roof responsibility"
          value={
            roofResponsibilityLabel[property.roof_responsibility] ?? property.roof_responsibility
          }
        />
        <DetailRow
          label="Access notes"
          value={property.access_notes ?? "No access notes recorded."}
        />
      </div>

      <SectionHeader title="Tenant" />
      <div className="mt-2 divide-y divide-border">
        <DetailRow label="Name" value={tenant.display_name} />
        <DetailRow label="Phone" value={tenant.phone_e164 ?? "No phone on file"} />
        <DetailRow label="Email" value={tenant.email ?? "No email on file"} />
        <DetailRow label="Preferred channel" value={titleCase(tenant.preferred_channel)} />
        <DetailRow label="Contact allowed" value={tenant.contact_allowed ? "Yes" : "No"} />
        <DetailRow
          label="Accessibility notes"
          value={tenant.accessibility_notes ?? "None recorded."}
        />
      </div>
    </Card>
  );
}

/** No file-attachment model exists anywhere in this codebase yet (backend
 * or frontend) -- this is an honest empty state, not a stand-in for a real
 * upload feature (that's separate, larger scope). Making the tab navigate
 * and render this is the fix for the dead button; inventing a fake file
 * list would not be. */
function FilesColumn() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 p-10 text-center">
      <FileQuestion className="h-8 w-8 text-muted-foreground" />
      <p className="text-[13px] font-medium">No files attached to this ticket yet.</p>
      <p className="max-w-xs text-xs text-muted-foreground">
        File uploads aren't part of this build. Evidence for this ticket lives in the call
        recordings and transcripts under the Calls tab.
      </p>
    </Card>
  );
}

const workOrderKindLabel: Record<string, string> = {
  REPAIR: "Repair",
  SCAFFOLD_INSTALL: "Scaffold install",
  SCAFFOLD_REMOVE: "Scaffold removal",
};

/** Real quote_pence/approved_limit_pence per work order, already on the
 * snapshot -- labelled as a quote/approved ceiling rather than an actual
 * invoiced cost, since that's what these fields actually are (docs/06). */
function CostsColumn({ workOrders }: { workOrders: WorkOrder[] }) {
  return (
    <Card className="p-5">
      <SectionHeader
        title="Costs"
        subtitle="Quotes and approved spend limits per work order -- not final invoiced costs."
      />
      {workOrders.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">No costs recorded yet.</p>
      )}
      <ul className="mt-4 space-y-3">
        {workOrders.map((wo) => (
          <li key={wo.id} className="rounded-lg border border-border p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[13px] font-semibold">
                  {workOrderKindLabel[wo.kind] ?? titleCase(wo.kind)}
                  <Pill tone="gray">{titleCase(wo.trade)}</Pill>
                </div>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{wo.scope}</p>
              </div>
              <Pill tone={wo.status === "COMPLETED" ? "green" : "blue"}>
                {titleCase(wo.status)}
              </Pill>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-2.5 text-xs">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <PoundSterling className="h-3 w-3" /> Quoted
              </div>
              <div className="text-right font-medium">
                {formatPence(wo.quote_pence) ?? "No quote recorded"}
              </div>
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <PoundSterling className="h-3 w-3" /> Approved limit
              </div>
              <div className="text-right font-medium">
                {formatPence(wo.approved_limit_pence) ?? "No approved limit set"}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
