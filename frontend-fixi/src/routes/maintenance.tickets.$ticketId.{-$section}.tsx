import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  Copy,
  Mail,
  MapPin,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Phone,
  Share2,
} from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill, StatusBadge, UrgencyBadge } from "@/components/fixi/Badge";
import { CaseLifecycleActions } from "@/components/fixi/CaseLifecycleActions";
import { useCaseDetail } from "@/hooks/use-case-detail";
import { useCaseEvents } from "@/hooks/use-case-events";
import { useCancelAppointment } from "@/hooks/use-case-actions";
import { usePropertyHistory } from "@/hooks/use-property-history";
import type { Appointment, CaseSnapshot } from "@/api/types";
import { statusTone } from "@/lib/fixi-data";
import { formatDateRange, formatRelative, initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const sections = ["summary", "timeline"] as const;
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
            <h1 className="mt-2 max-w-2xl text-2xl font-bold tracking-tight" title={c.title}>
              #{c.case_number} – <span className="line-clamp-2">{c.title}</span>
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
            <StatusBadge status={c.status} className="h-9 px-3.5 text-sm" />
            <CaseLifecycleActions caseId={c.id} status={c.status} version={c.version} />
          </div>
        </div>

        <div className="mt-5 flex gap-6 border-b border-border text-sm">
          {["Overview", "Property", "Files", "Costs"].map((t, i) => (
            <button
              key={t}
              className={cn(
                "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
                i === 0
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-1.5">
          <SectionLink ticketId={ticketId} section={undefined} active={section === null}>
            All
          </SectionLink>
          <SectionLink ticketId={ticketId} section="summary" active={section === "summary"}>
            Summary
          </SectionLink>
          <SectionLink ticketId={ticketId} section="timeline" active={section === "timeline"}>
            Timeline
          </SectionLink>
        </div>

        <div
          className={cn("mt-3 grid gap-4", section === null ? "xl:grid-cols-2" : "xl:grid-cols-1")}
        >
          {show("summary") && <SummaryColumn snapshot={snapshot} />}
          {show("timeline") && <TimelineColumn caseId={c.id} />}
        </div>
      </div>
    </AppShell>
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

function TimelineColumn({ caseId }: { caseId: string }) {
  const events = useCaseEvents(caseId);
  const items = events.data?.items ?? [];

  return (
    <Card className="p-5">
      <SectionHeader
        title="Agent timeline"
        subtitle="What the AI agent has done and what's next."
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
            <li key={item.id} className="relative flex gap-3 pb-5 last:pb-0">
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
      </ol>
    </Card>
  );
}
