import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Mail,
  MapPin,
  Phone,
  PhoneCall,
} from "lucide-react";
import { AgentActivity } from "@/components/fixi/AgentActivity";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill, StatusBadge, UrgencyBadge } from "@/components/fixi/Badge";
import { CaseLifecycleActions } from "@/components/fixi/CaseLifecycleActions";
import { CaseProgress } from "@/components/fixi/CaseProgress";
import { CaseToolbar } from "@/components/fixi/CaseToolbar";
import { CostsPanel } from "@/components/fixi/CostsPanel";
import { DecisionCard } from "@/components/fixi/DecisionCard";
import { DocumentsPanel } from "@/components/fixi/DocumentsPanel";
import { RescheduleDialog } from "@/components/fixi/RescheduleDialog";
import { SkeletonCards } from "@/components/fixi/Skeleton";
import { WorkGraph } from "@/components/fixi/WorkGraph";
import { RecordFieldUpdateDialog } from "@/components/fixi/RecordFieldUpdateDialog";
import { MessagesPanel } from "@/components/fixi/MessagesPanel";
import { authHeader, BASE_URL } from "@/api/client";
import { useRetryRecording } from "@/hooks/use-case-actions";
import { useCaseDetail } from "@/hooks/use-case-detail";
import { useCaseEvents } from "@/hooks/use-case-events";
import { usePropertyHistory } from "@/hooks/use-property-history";
import { useAuthedCreds } from "@/lib/auth-context";
import type { Appointment, CaseSnapshot, Communication, Recording } from "@/api/types";
import { statusTone, STATUS_LABEL } from "@/lib/fixi-data";
import { formatDateRange, formatPence, formatRelative, initials, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// "property"/"files"/"costs" used to be a second, dead button row above
// this one ("Overview/Property/Files/Costs" with no onClick at all) --
// folded into this single functional tab set instead of leaving two rows
// where only one worked. "Overview" (the null/undefined section) keeps its
// old "All" behaviour: summary + timeline + calls together.
// "work" is new: the work orders on this case and any dependency blocking
// one on another (e.g. a scaffold install blocking a roof repair) --
// previously nowhere on this UI (CaseSnapshot.dependencies was typed
// `unknown[]` and unrendered). Deliberately not folded into "Overview": a
// graph needs real vertical room, and most cases render it as one node,
// which reads fine as its own tab and would look sparse crammed in above.
// "messages" is also new: a read-only tenant/contractor/operator message
// thread (GET /cases/{id}/messages, backend/app/schemas.py Message). Chat
// history is never authoritative state and the AI coordinator never reads
// it (CLAUDE.md) -- this is a display-only convenience layer, same spirit
// as "files": renders only what the read-only endpoint returns, no
// composer wired to a send endpoint that doesn't exist yet.
const sections = [
  "summary",
  "timeline",
  "agent",
  "calls",
  "work",
  "property",
  "files",
  "costs",
  "messages",
] as const;
type Section = (typeof sections)[number];

export const Route = createFileRoute("/maintenance/tickets/$ticketId/{-$section}")({
  loader: ({ params }) => {
    if (params.section && !sections.includes(params.section as Section)) throw notFound();
    return { section: (params.section as Section | undefined) ?? null };
  },
  head: ({ loaderData }) => {
    // params.ticketId is the case UUID, which makes a useless browser-tab
    // label. `head` runs before the snapshot loads, so the real
    // "#42 – Slipped tiles" title is set from the component once the
    // case arrives (see the effect in CasePage); this is the placeholder
    // shown for the moment before that.
    const title = `Ticket — Fixi${loaderData?.section ? ` · ${cap(loaderData.section)}` : ""}`;
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

  // The route's `head` cannot know the case number -- it runs before the
  // snapshot loads, and params.ticketId is a UUID. Set the real title once
  // the case arrives so a pinned tab or a bookmark reads "#42 – Slipped
  // tiles" rather than a hex string. Must sit above the early returns
  // below: hooks cannot be called conditionally.
  const loadedTitle = detail.data
    ? `#${detail.data.snapshot.case.case_number} – ${detail.data.snapshot.case.title}`
    : null;
  useEffect(() => {
    if (loadedTitle === null || typeof document === "undefined") return;
    document.title = `${loadedTitle} — Fixi`;
  }, [loadedTitle]);

  if (detail.isLoading) {
    return (
      <AppShell>
        <div className="mx-auto w-full max-w-page px-6 py-5 text-strong text-muted-foreground xl:px-7">
          Loading ticket…
        </div>
      </AppShell>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <AppShell>
        <div className="mx-auto w-full max-w-page px-6 py-5 xl:px-7">
          <Link
            to="/maintenance"
            className="flex items-center gap-1.5 text-strong text-muted-foreground hover:text-foreground"
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
      <div className="mx-auto w-full max-w-page px-6 py-5 xl:px-7">
        {/* Header budget (docs/27 section 4.5). This used to be five
         * stacked rows -- back link, badge, title, address, updated --
         * plus a two-row action cluster and a row holding one button,
         * which cost 526px before any content on a 1226px viewport (43%
         * of the window, on all ten tabs). It is now two rows: the back
         * arrow and badge join the title line, address and freshness
         * share one meta line, and every action sits in a single
         * wrapping cluster. */}
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <Link
                to="/maintenance"
                aria-label="Back to tickets"
                title="Back to tickets"
                className="-ml-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-fast ease-fixi hover:bg-accent hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
              </Link>
              <UrgencyBadge urgency={c.risk.urgency} />
              <h1
                className="line-clamp-1 min-w-0 text-title font-bold tracking-tight"
                title={c.title}
              >
                #{c.case_number} – {c.title}
              </h1>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 pl-8 text-strong text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5 shrink-0" /> {address}
              </span>
              <button
                type="button"
                onClick={() => void navigator.clipboard?.writeText(address)}
                title="Copy address"
                aria-label="Copy address"
              >
                <Copy className="h-3.5 w-3.5 cursor-pointer transition-colors duration-fast hover:text-foreground" />
              </button>
              <span aria-hidden="true">·</span>
              {/* docs/18 line 34 lists "last updated" as part of the case
               * header. The field was always on the snapshot and never
               * rendered, so nothing on the page said how fresh it was. */}
              <span>
                Updated {formatRelative(c.updated_at)} · version {c.version}
              </span>
            </div>
          </div>
          {/* One wrapping cluster instead of two stacked rows. The
           * "Record an update" trigger moved in here from its own
           * full-width row below the progress rail. */}
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {snapshot.agent_active && (
              <span className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-body font-medium text-muted-foreground shadow-card">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Agent thinking…
              </span>
            )}
            <StatusBadge status={c.status} />
            <CaseLifecycleActions caseId={c.id} status={c.status} version={c.version} />
            <CaseToolbar snapshot={snapshot} />
            {/* There's no live contractor/tenant phone channel in this MVP
             * -- this is how the hero demo path (contractor reports
             * scaffolding needed, tenant confirms a repair) gets driven
             * from the UI at all: an operator manually feeds in what a
             * real call would have reported. See
             * RecordFieldUpdateDialog.tsx. */}
            <RecordFieldUpdateDialog
              caseId={c.id}
              appointments={snapshot.appointments}
              workOrders={snapshot.work_orders}
            />
          </div>
        </div>

        <CaseProgress snapshot={snapshot} />

        <DecisionCard caseId={c.id} pendingActions={snapshot.pending_actions} snapshot={snapshot} />

        {/* Sticky: the header above is ~300px, so on a long tab the tabs
         * would otherwise scroll out of reach. `-mx-6` lets the border
         * run full-bleed inside the padded container. */}
        <div className="sticky top-0 z-30 -mx-6 mt-4 border-b border-border bg-background/85 px-6 backdrop-blur xl:-mx-7 xl:px-7">
          <div className="flex flex-wrap items-center gap-0.5">
            <SectionLink ticketId={ticketId} section={undefined} active={section === null}>
              Overview
            </SectionLink>
            <SectionLink ticketId={ticketId} section="summary" active={section === "summary"}>
              Summary
            </SectionLink>
            <SectionLink ticketId={ticketId} section="timeline" active={section === "timeline"}>
              Timeline
            </SectionLink>
            <SectionLink ticketId={ticketId} section="agent" active={section === "agent"}>
              Agent
            </SectionLink>
            <SectionLink ticketId={ticketId} section="calls" active={section === "calls"}>
              Calls
            </SectionLink>
            <SectionLink ticketId={ticketId} section="work" active={section === "work"}>
              Work
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
            <SectionLink ticketId={ticketId} section="messages" active={section === "messages"}>
              Messages
            </SectionLink>
          </div>
        </div>

        <div
          className={cn("mt-4 grid gap-4", section === null ? "xl:grid-cols-2" : "xl:grid-cols-1")}
        >
          {show("summary") && <SummaryColumn snapshot={snapshot} />}
          {show("timeline") && (
            <TimelineColumn
              caseId={c.id}
              agentActive={snapshot.agent_active}
              ticketId={ticketId}
              showViewAll={section === null}
            />
          )}
          {show("agent") && <AgentActivity snapshot={snapshot} />}
          {show("calls") && (
            <CallsColumn caseId={snapshot.case.id} communications={snapshot.communications} />
          )}
          {section === "work" && (
            <WorkGraph
              workOrders={snapshot.work_orders}
              dependencies={snapshot.dependencies}
              appointments={snapshot.appointments}
            />
          )}
          {section === "property" && <PropertyColumn snapshot={snapshot} />}
          {section === "files" && (
            <DocumentsPanel caseId={c.id} evidenceRefs={snapshot.issue.evidence_refs} />
          )}
          {section === "costs" && <CostsPanel caseId={c.id} workOrders={snapshot.work_orders} />}
          {section === "messages" && <MessagesPanel caseId={c.id} />}
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

function CallsColumn({
  caseId,
  communications,
}: {
  caseId: string;
  communications: Communication[];
}) {
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
          <CallRow key={comm.id} caseId={caseId} comm={comm} />
        ))}
      </ul>
    </Card>
  );
}

/** What to show when there is no playable audio.
 *
 * Previously this was one line -- "Recording: failed" -- which threw away
 * the two things that make it actionable: `recording.error_code`, which is
 * captured and says WHY, and the retry endpoint, which existed with no
 * caller. CLAUDE.md requires call recordings be persisted, correlated and
 * playable, so a failed fetch being a dead end on screen was a real gap.
 *
 * PENDING is a normal in-flight state, not a failure, and is worded as
 * such -- retry is still offered because a job can be lost. */
function RecordingUnavailable({
  caseId,
  communicationId,
  recording,
}: {
  caseId: string;
  communicationId: string;
  recording: Recording;
}) {
  const retry = useRetryRecording(caseId);
  const failed = recording.status === "FAILED";

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">
          {recording.status === "PENDING"
            ? "Recording: still being fetched."
            : failed
              ? "Recording: the fetch failed."
              : "Recording: not available for this call."}
        </p>
        {recording.error_code && (
          <p className="mt-0.5 text-micro text-muted-foreground">
            Reason: <span className="font-mono">{recording.error_code}</span>
          </p>
        )}
      </div>
      {recording.status !== "UNAVAILABLE" && (
        <button
          type="button"
          onClick={() => retry.mutate(communicationId)}
          disabled={retry.isPending}
          className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-50"
        >
          {retry.isPending ? "Retrying…" : "Retry fetch"}
        </button>
      )}
    </div>
  );
}

function CallRow({ caseId, comm }: { caseId: string; comm: Communication }) {
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
            <div className="flex items-center gap-2 text-strong font-semibold">
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
        <span className="shrink-0 text-micro text-muted-foreground">
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
            <RecordingUnavailable
              caseId={caseId}
              communicationId={comm.id}
              recording={comm.recording}
            />
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
          {/* docs/18 line 38 asks the communication drawer to show the
           * provider's conversation id. It is captured on every real call
           * and was never rendered, so a LIVE call could not be matched
           * against the provider's own dashboard when something went
           * wrong. */}
          {comm.provider_conversation_id && (
            <p className="mt-3 border-t border-border pt-2 text-micro text-muted-foreground">
              Conversation <span className="font-mono">{comm.provider_conversation_id}</span>
            </p>
          )}
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
        // Underline, not a pill: the pill was identical to the date-range
        // filter buttons on Insights and Reports, so navigation and
        // filtering were indistinguishable. PropertyTabs already uses an
        // underline -- this makes it the one navigation idiom (docs/27).
        "relative h-11 px-3 text-strong font-medium leading-[44px] transition-colors duration-fast ease-fixi",
        active
          ? "text-foreground after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-foreground"
          : "text-muted-foreground hover:text-foreground",
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
        <h2 className="text-section font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-strong font-semibold">{children}</div>;
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

/** Was a plain non-interactive button (no onClick, no href) for
 * MessageSquare/Mail/Phone. MessageSquare is gone entirely -- this app has
 * no messaging/chat concept (see AppShell's nav comment). Mail/Phone are
 * now real mailto:/tel: links off the tenant's actual contact fields, and
 * honour contact_allowed: a tenant who hasn't consented to contact
 * doesn't get a live link even if a number/email is on file. */
function IconButton({
  icon: Icon,
  href,
  title,
}: {
  icon: typeof Phone;
  href?: string | undefined;
  title: string;
}) {
  const className =
    "flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-card disabled:hover:text-muted-foreground";
  if (!href) {
    return (
      <button type="button" disabled title={title} className={className}>
        <Icon className="h-3.5 w-3.5" />
      </button>
    );
  }
  return (
    <a href={href} title={title} className={className}>
      <Icon className="h-3.5 w-3.5" />
    </a>
  );
}

const appointmentStatusTone: Record<Appointment["status"], "amber" | "green" | "gray"> = {
  PENDING: "amber",
  CONFIRMED: "green",
  FINISHED: "gray",
  CANCELLED: "gray",
};

/** A PENDING appointment (the only kind RescheduleDialog ever creates --
 * an operator-arranged slot is never auto-confirmed, docs/19) must read as
 * pending right here in the header, not only inside the dialog that made
 * it -- showing a confident date/time with no status would be the same
 * "confirmed" fabrication the rest of this app avoids. */
function NextAppointmentRow({ caseId, appointment }: { caseId: string; appointment: Appointment }) {
  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);
  return (
    <div className="mt-2 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
          <Calendar className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-strong font-medium">{date}</div>
          <div className="text-xs text-muted-foreground">{time}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <Pill tone={appointmentStatusTone[appointment.status]}>
              {appointment.status === "PENDING"
                ? "Pending — contractor has not confirmed"
                : titleCase(appointment.status)}
            </Pill>
            {/* A slot booked through MockBookingConnector is CONFIRMED in
             * the domain sense and simulated in every other sense: the
             * connector invents the availability and no real contractor
             * ever saw it. Without this the green pill is
             * indistinguishable from a genuine provider confirmation.
             * Communications and research already carry a provenance
             * badge; appointments did not. */}
            {appointment.connector === "MOCK" && (
              <Pill
                tone="amber"
                title="Booked against a simulated calendar. No real contractor has been contacted or has agreed this slot."
              >
                Simulated booking
              </Pill>
            )}
          </div>
        </div>
      </div>
      <RescheduleDialog caseId={caseId} appointment={appointment} />
    </div>
  );
}

/** Navigates to an internal profile/history page. Plain `<a>` rather than a
 * typed `<Link>` for `/tenants/$tenantId` and `/contractors/$contractorId`:
 * neither route exists in this checkout yet (other agents are adding them
 * concurrently -- see NEEDS_FROM_ROOT_ticket.md), and TanStack's `to` prop
 * is checked against the generated route tree, so a typed `Link` to a route
 * that doesn't exist yet fails `tsc` until it lands. A full navigation
 * still reaches the right page once it does. */
/** A real client-side <Link>, not a plain <a>.
 *
 * These targets (/tenants/$tenantId, /contractors/$contractorId) are
 * registered routes; the anchor here predated them and triggered a full
 * page reload, discarding the loaded case and every cached query for no
 * reason. `title` alone was also the whole accessible name -- an
 * icon-only control needs an explicit one. */
const profileLinkClass =
  "flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground";

function TenantProfileLink({ tenantId }: { tenantId: string }) {
  return (
    <Link
      to="/tenants/$tenantId"
      params={{ tenantId }}
      title="View tenant profile"
      aria-label="View tenant profile"
      className={profileLinkClass}
    >
      <ExternalLink className="h-3.5 w-3.5" />
    </Link>
  );
}

function ContractorProfileLink({ contractorId }: { contractorId: string }) {
  return (
    <Link
      to="/contractors/$contractorId"
      params={{ contractorId }}
      title="View contractor profile"
      aria-label="View contractor profile"
      className={profileLinkClass}
    >
      <ExternalLink className="h-3.5 w-3.5" />
    </Link>
  );
}

function SummaryColumn({ snapshot }: { snapshot: CaseSnapshot }) {
  const {
    case: c,
    issue,
    tenant,
    assigned_contractor,
    next_appointment,
    property,
    latest_reports,
    appointments,
    work_orders,
    approved_contractors,
    availability,
    policy_snapshot,
  } = snapshot;
  const propertyHistory = usePropertyHistory(property.id);

  // "No appointment scheduled yet" is only true if none was EVER booked.
  // next_appointment is filtered to CONFIRMED/PENDING visits still in the
  // future (services.py), so a case whose only visit has already happened
  // -- the common "attended, didn't fix it, now blocked" shape -- was being
  // described as never booked. That reads as nothing happening when in fact
  // the visit is the reason the case is stuck.
  const pastAppointments = [...appointments].sort((a, b) =>
    a.start_at < b.start_at ? 1 : a.start_at > b.start_at ? -1 : 0,
  );
  const lastAppointment = next_appointment ? null : (pastAppointments[0] ?? null);

  // The roster is portfolio-wide, not per-case: with 18 approved
  // contractors, listing all of them buries everything below it. Rank by
  // relevance to THIS case -- whoever is assigned, then anyone qualified
  // for a trade this case actually needs -- and keep the rest behind a
  // count rather than dropping them silently.
  const neededTrades = new Set(work_orders.map((w) => w.trade));
  const rankedContractors = [...approved_contractors].sort((a, b) => {
    const score = (x: (typeof approved_contractors)[number]) =>
      (assigned_contractor?.id === x.id ? 2 : 0) +
      (x.trades.some((t) => neededTrades.has(t as (typeof work_orders)[number]["trade"])) ? 1 : 0);
    return score(b) - score(a);
  });
  const RELEVANT_CONTRACTOR_LIMIT = 5;
  const shownContractors = rankedContractors.slice(0, RELEVANT_CONTRACTOR_LIMIT);
  const hiddenContractorCount = rankedContractors.length - shownContractors.length;

  // Real mailto:/tel: targets off the tenant's actual contact fields --
  // gated on contact_allowed (a real field, not assumed) so a tenant who
  // hasn't consented to contact never gets a live link, even if a
  // number/email happens to be on file.
  const emailHref = tenant.contact_allowed && tenant.email ? `mailto:${tenant.email}` : undefined;
  const emailTitle = !tenant.contact_allowed
    ? "Tenant has not consented to contact"
    : (tenant.email ?? "No email on file");
  const phoneHref =
    tenant.contact_allowed && tenant.phone_e164 ? `tel:${tenant.phone_e164}` : undefined;
  const phoneTitle = !tenant.contact_allowed
    ? "Tenant has not consented to contact"
    : (tenant.phone_e164 ?? "No phone number on file");

  return (
    <Card className="p-5">
      <SectionHeader title="Case overview" />
      <p className="mt-2 text-strong leading-relaxed text-muted-foreground">{issue.description}</p>
      {c.last_decision_summary && (
        <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-strong leading-relaxed text-muted-foreground">
          {c.last_decision_summary}
        </p>
      )}

      <div className="mt-5 border-t border-border pt-4">
        <Label>Tenant</Label>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar initials={initials(tenant.display_name)} tone="gray" />
            <div className="leading-tight">
              <div className="text-strong font-medium">{tenant.display_name}</div>
              <div className="text-xs text-muted-foreground">
                {tenant.phone_e164 ?? tenant.email ?? "No contact on file"}
              </div>
            </div>
          </div>
          <div className="flex gap-1.5">
            <IconButton icon={Mail} href={emailHref} title={emailTitle} />
            <IconButton icon={Phone} href={phoneHref} title={phoneTitle} />
            <TenantProfileLink tenantId={tenant.id} />
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Assigned contractor</Label>
        {assigned_contractor ? (
          <div className="mt-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Avatar initials={initials(assigned_contractor.display_name)} tone="green" />
              <div className="leading-tight">
                <div className="text-strong font-medium">{assigned_contractor.display_name}</div>
                <div className="text-xs text-muted-foreground">
                  {assigned_contractor.trade ?? "—"}
                </div>
                {assigned_contractor.phone && (
                  <div className="text-xs text-muted-foreground">{assigned_contractor.phone}</div>
                )}
              </div>
            </div>
            <ContractorProfileLink contractorId={assigned_contractor.id} />
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">No contractor assigned yet.</p>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Next appointment</Label>
        {next_appointment ? (
          <NextAppointmentRow caseId={c.id} appointment={next_appointment} />
        ) : lastAppointment ? (
          <div className="mt-2 space-y-1">
            <p className="text-xs text-muted-foreground">
              Nothing upcoming. Last visit {formatRelative(lastAppointment.start_at)}
              {lastAppointment.attempt_number > 1
                ? ` (attempt ${lastAppointment.attempt_number})`
                : ""}
              .
            </p>
            <p className="text-xs">
              <span className="text-muted-foreground">Outcome: </span>
              <span className="font-medium">
                {lastAppointment.visit_outcome
                  ? titleCase(lastAppointment.visit_outcome)
                  : titleCase(lastAppointment.status)}
              </span>
            </p>
            <p className="text-micro text-muted-foreground">
              {appointments.length} visit{appointments.length === 1 ? "" : "s"} on this case.
            </p>
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">No appointment scheduled yet.</p>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Approved contractors</Label>
        {/* The roster the coordinator is allowed to choose from. Distinct
         * from "Assigned contractor" above: a case routinely has several
         * approved suppliers and nobody assigned, which previously looked
         * like the system knew nobody. The API has always sent this; it was
         * typed `unknown[]` and rendered nowhere until 2026-09-21. */}
        {approved_contractors.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            No approved contractor covers this case yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {shownContractors.map((ac) => (
              <li key={ac.id} className="flex items-start justify-between gap-2 text-xs">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{ac.display_name}</span>
                  <span className="block text-muted-foreground">
                    {ac.trades.map(titleCase).join(", ") || "—"}
                    {ac.service_postcodes.length > 0 && ` · ${ac.service_postcodes.join(", ")}`}
                  </span>
                </span>
                {assigned_contractor?.id === ac.id && <Pill tone="green">Assigned</Pill>}
              </li>
            ))}
          </ul>
        )}
        {hiddenContractorCount > 0 && (
          <p className="mt-1.5 text-micro text-muted-foreground">
            + {hiddenContractorCount} more approved for other trades or areas.
          </p>
        )}
        {typeof policy_snapshot.ordinary_authority_limit_pence === "number" && (
          <p className="mt-2 text-micro text-muted-foreground">
            Auto-approval limit {formatPence(policy_snapshot.ordinary_authority_limit_pence)} —
            above this, an action waits for a human.
          </p>
        )}
        {availability.length > 0 && (
          <p className="mt-1 text-micro text-muted-foreground">
            {availability.length} tenant availability window
            {availability.length === 1 ? "" : "s"} on file.
          </p>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Contractor reports</Label>
        {/* Real ContractorReportModel rows (backend/app/schemas.py
         * ContractorReport, up to the 10 most recent) -- populated by a
         * real ElevenLabs contractor call, or by an operator writing one
         * up in the "Record an update" dialog above. Untyped/unread
         * before this (CaseSnapshot.latest_reports was `unknown[]`); this
         * is the fix, and the one place these reports render. */}
        {latest_reports.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">No contractor reports yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {latest_reports.map((r) => (
              <li key={r.id} className="rounded-lg border border-border p-2.5 text-xs">
                {/* Adjacent, not justify-between: the provenance badge
                 * and the time it was observed are two facts about the
                 * same report, and pinning the timestamp to the card's
                 * right edge put 657px of nothing between them. */}
                <div className="flex items-center gap-2">
                  <Pill tone={r.provenance === "LIVE" ? "blue" : "gray"}>{r.provenance}</Pill>
                  <span className="text-muted-foreground">{formatRelative(r.observed_at)}</span>
                </div>
                <p className="mt-1.5 leading-relaxed">{r.text}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Property history</Label>
        {propertyHistory.isLoading && <SkeletonCards className="mt-2" count={3} height="h-9" />}
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
                <Pill tone={statusTone(h.status)}>{STATUS_LABEL[h.status] ?? h.status}</Pill>
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

function TimelineColumn({
  caseId,
  agentActive,
  ticketId,
  showViewAll,
}: {
  caseId: string;
  agentActive: boolean;
  ticketId: string;
  showViewAll: boolean;
}) {
  const events = useCaseEvents(caseId);
  const items = events.data?.items ?? [];

  return (
    <Card className="p-5">
      <SectionHeader
        title="Agent timeline"
        subtitle="What the AI agent has done and what's next."
        action={
          agentActive || showViewAll ? (
            <div className="flex items-center gap-3">
              {agentActive && (
                <span
                  className="flex items-center gap-1.5 text-micro font-medium text-muted-foreground"
                  title="The coordinator is actively working on this case right now"
                >
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Thinking…
                </span>
              )}
              {showViewAll && (
                <Link
                  to="/maintenance/tickets/$ticketId/{-$section}"
                  params={{ ticketId, section: "timeline" }}
                  className="text-micro font-medium text-primary hover:underline"
                >
                  View all
                </Link>
              )}
            </div>
          ) : undefined
        }
      />
      {events.isLoading && <SkeletonCards className="mt-4" count={4} height="h-16" />}
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
              {/* A two-track grid rather than `justify-between` across the
               * whole row: at 2552px that flung the timestamp 2073px away
               * from the title it belongs to. The first track caps at the
               * longest sensible title, so the timestamp lands just past
               * it instead of at the far wall (docs/27 section 4.4). */}
              <div className="grid min-w-0 flex-1 grid-cols-[minmax(0,68ch)_auto] items-baseline gap-x-6">
                <div className="text-strong font-semibold">{item.display_title}</div>
                <span className="justify-self-start whitespace-nowrap text-micro text-muted-foreground">
                  {formatRelative(item.occurred_at)}
                </span>
                <p className="col-span-2 mt-0.5 max-w-prose-fixi text-body leading-relaxed text-muted-foreground">
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
              <div className="text-strong font-semibold text-muted-foreground">
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
    <div className="flex items-start justify-between gap-4 py-2 text-strong">
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

// FilesColumn/CostsColumn (the old dead-button placeholder and the
// per-work-order-only cost view) are replaced by DocumentsPanel.tsx and
// CostsPanel.tsx respectively -- see the Files/Costs tab wiring above.
