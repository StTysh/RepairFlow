import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  Building2,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock3,
  HardHat,
  MessageCircle,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { Metric } from "@/components/fixi/Metric";
import {
  useOverview,
  type NeedsAttentionItem,
  type OverviewActivityItem,
  type OverviewAppointmentItem,
} from "@/hooks/use-analytics";
import { formatDateRange, formatRelative, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Replaces the old `beforeLoad: redirect to /maintenance` stub -- "/" is
// now the real portfolio landing page (Overview). "/" is also the one
// route this app prerenders (see properties.$propertyId.history.tsx's
// routing note), so this stays the natural first screen for a hard load.
export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview — Fixi" },
      {
        name: "description",
        content:
          "Portfolio at a glance: what needs attention, upcoming visits and recent activity.",
      },
      { property: "og:title", content: "Overview — Fixi" },
    ],
  }),
  component: OverviewPage,
});

const NEEDS_ATTENTION_ICON: Record<NeedsAttentionItem["reason"], LucideIcon> = {
  AWAITING_APPROVAL: MessageCircle,
  ESCALATED: AlertTriangle,
  OVERDUE_FOLLOW_UP: Clock3,
};

const NEEDS_ATTENTION_TONE_CLASS: Record<NeedsAttentionItem["reason"], string> = {
  AWAITING_APPROVAL: "bg-status-amber text-status-amber-foreground",
  ESCALATED: "bg-status-red text-status-red-foreground",
  OVERDUE_FOLLOW_UP: "bg-status-orange text-status-orange-foreground",
};

const NEEDS_ATTENTION_LABEL: Record<NeedsAttentionItem["reason"], string> = {
  AWAITING_APPROVAL: "Awaiting approval",
  ESCALATED: "Escalated",
  OVERDUE_FOLLOW_UP: "Overdue follow-up",
};

// overview.py's AttentionItemResponse.reason is a plain `str`, not a
// Pydantic Literal/Enum -- analytics.needs_attention() only ever emits the
// 3 values above today, but the response model doesn't guarantee that will
// stay true. Indexing the three Records above directly on an unrecognised
// value is exactly the crash this page was fixed for (item.kind was
// undefined for the same reason); these fall back to a generic
// presentation instead of `undefined` reaching <Icon>, the same way
// tenants.$tenantId.tsx's CaseStatusPill already guards an unrecognised
// status rather than crashing StatusBadge.
function attentionIcon(reason: string): LucideIcon {
  return NEEDS_ATTENTION_ICON[reason as NeedsAttentionItem["reason"]] ?? AlertTriangle;
}
function attentionTone(reason: string): string {
  return (
    NEEDS_ATTENTION_TONE_CLASS[reason as NeedsAttentionItem["reason"]] ??
    "bg-muted text-muted-foreground"
  );
}
function attentionLabel(reason: string): string {
  return NEEDS_ATTENTION_LABEL[reason as NeedsAttentionItem["reason"]] ?? titleCase(reason);
}

function OverviewPage() {
  const overview = useOverview();
  const data = overview.data;

  function retryOverview() {
    void overview.refetch();
  }

  const needsAttention = data?.needs_attention ?? [];
  const upcoming = data?.upcoming_appointments ?? [];
  const activity = data?.recent_activity ?? [];

  // There is no single "open cases" field on the wire -- status_counts
  // breaks cases down by all 5 CaseStatus values. "Open" is the 3
  // non-terminal ones (ACTIVE, AWAITING_CONFIRMATION, ESCALATED); RESOLVED
  // and CANCELLED are terminal and excluded, matching
  // analytics.case_is_open's definition on the backend.
  const openCases = data
    ? data.status_counts.active +
      data.status_counts.awaiting_confirmation +
      data.status_counts.escalated
    : undefined;

  return (
    <AppShell>
      <PageContainer
        title="Overview"
        description="Portfolio at a glance: what needs attention, upcoming visits and recent activity."
      >
        {overview.isError ? (
          <ErrorState
            {...(overview.error instanceof Error ? { detail: overview.error.message } : {})}
            onRetry={retryOverview}
          />
        ) : (
          <>
            {/* --- Portfolio metrics ----------------------------------- */}
            <section
              className="grid grid-cols-2 gap-3 md:grid-cols-4"
              aria-label="Portfolio metrics"
            >
              {overview.isLoading ? (
                <LoadingRows rows={4} className="col-span-2 md:col-span-4" />
              ) : (
                <>
                  <MetricLink
                    icon={Building2}
                    value={data?.property_count}
                    label="Properties"
                    linkTo="/properties"
                  />
                  <MetricLink
                    icon={Users}
                    value={data?.tenant_count}
                    label="Tenants"
                    // /tenants isn't registered in the route tree yet (a
                    // sibling agent owns that page/route this session) --
                    // a plain anchor still performs a real navigation via
                    // the SPA fallback shell once it exists, same pattern
                    // __root.tsx's ErrorComponent already uses for "Go
                    // home". See NEEDS_FROM_ROOT_analytics.md.
                    linkTo="/tenants"
                  />
                  <MetricLink
                    icon={HardHat}
                    value={data?.approved_contractor_count}
                    label="Approved contractors"
                    linkTo="/contractors"
                  />
                  <MetricLink
                    icon={Wrench}
                    value={openCases}
                    label="Open cases"
                    linkTo="/maintenance"
                  />
                </>
              )}
            </section>

            {/* --- Needs attention (most important block) --------------- */}
            <section className="mt-5">
              <Card className="p-4">
                <div className="flex items-center gap-2">
                  <h2 className="text-section font-semibold">Needs attention</h2>
                  {!overview.isLoading && needsAttention.length > 0 && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-micro font-bold text-destructive-foreground">
                      {needsAttention.length}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Awaiting approval, escalated, or past a promised follow-up date.
                </p>

                <div className="mt-3">
                  {overview.isLoading ? (
                    <LoadingRows rows={3} />
                  ) : needsAttention.length === 0 ? (
                    <EmptyState
                      icon={CheckCircle2}
                      title="All caught up"
                      description="No case is awaiting approval, escalated, or overdue right now."
                    />
                  ) : (
                    <ul className="divide-y divide-border">
                      {needsAttention.map((item) => {
                        const Icon = attentionIcon(item.reason);
                        return (
                          // Not just case_id+reason: an AWAITING_APPROVAL row
                          // is one ActionRecord, and a case can have more than
                          // one action pending at once, so those two fields
                          // alone can collide. occurred_at (action.updated_at
                          // for this branch) is real, already-fetched data,
                          // not a fabricated key.
                          <li key={`${item.case_id}-${item.reason}-${item.occurred_at}`}>
                            <Link
                              to="/maintenance/tickets/$ticketId/{-$section}"
                              params={{ ticketId: item.case_id, section: undefined }}
                              className="-mx-1 flex items-center gap-3 rounded-lg px-1 py-2.5 transition-colors hover:bg-accent/60"
                            >
                              <span
                                className={cn(
                                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                                  attentionTone(item.reason),
                                )}
                              >
                                <Icon className="h-4 w-4" />
                              </span>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="truncate text-xs font-semibold">
                                    #{item.case_number} · {item.case_title}
                                  </span>
                                  <span className="shrink-0 text-micro font-medium text-muted-foreground">
                                    {attentionLabel(item.reason)}
                                  </span>
                                </div>
                                <p className="mt-0.5 line-clamp-1 text-micro text-muted-foreground">
                                  {item.detail}
                                </p>
                              </div>
                              <span className="shrink-0 text-micro text-muted-foreground">
                                {formatRelative(item.occurred_at)}
                              </span>
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </Card>
            </section>

            {/* --- Upcoming appointments / Recent activity --------------- */}
            <section className="mt-4 grid gap-4 xl:grid-cols-2">
              <Card className="p-4">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-section font-semibold">Upcoming appointments</h2>
                  <Link
                    to="/maintenance"
                    className="text-micro font-medium text-primary hover:underline"
                  >
                    View all
                  </Link>
                </div>
                <div className="mt-3">
                  {overview.isLoading ? (
                    <LoadingRows rows={3} />
                  ) : upcoming.length === 0 ? (
                    <EmptyState
                      icon={Calendar}
                      title="No upcoming visits"
                      description="Once a contractor is booked, their next visit shows here. Use + New Ticket above to report an issue."
                      action={
                        <Link
                          to="/maintenance"
                          className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-accent"
                        >
                          Go to Maintenance
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="divide-y divide-border">
                      {upcoming.map((appt) => (
                        <AppointmentRow key={appt.appointment_id} appointment={appt} />
                      ))}
                    </ul>
                  )}
                </div>
              </Card>

              <Card className="p-4">
                <h2 className="text-section font-semibold">Recent activity</h2>
                <div className="mt-3">
                  {overview.isLoading ? (
                    <LoadingRows rows={3} />
                  ) : activity.length === 0 ? (
                    <EmptyState
                      icon={Wrench}
                      title="No activity yet"
                      description="Case updates will appear here as soon as something happens. Use + New Ticket above to report your first issue."
                      action={
                        <Link
                          to="/maintenance"
                          className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-accent"
                        >
                          View maintenance
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="divide-y divide-border">
                      {activity.map((event) => (
                        <ActivityRow key={event.event_id} event={event} />
                      ))}
                    </ul>
                  )}
                </div>
              </Card>
            </section>
          </>
        )}
      </PageContainer>
    </AppShell>
  );
}

/** One portfolio-metrics tile. Renders as a real `<Link>` when the
 * destination is already a registered route, or a plain `<a>` when it
 * isn't yet (see the /tenants, /contractors callers above) -- either way
 * the whole card is one clickable, keyboard-reachable target, matching the
 * density of maintenance.index.tsx's KPI cards. */
function MetricLink({
  icon: Icon,
  value,
  label,
  linkTo,
}: {
  icon: LucideIcon;
  value: number | undefined;
  label: string;
  linkTo: string;
}) {
  const content = (
    <>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <div className="text-metric font-bold tracking-tight">
          <Metric value={value ?? "—"} />
        </div>
        <div className="truncate text-xs text-muted-foreground">{label}</div>
      </div>
    </>
  );
  const className =
    "flex min-h-[92px] items-center gap-3 rounded-xl border border-border bg-card px-3.5 py-3 shadow-card transition-colors hover:bg-accent/60";

  // Every metric card is a real destination -- there is no plain-anchor
  // fallback any more, because there is no longer a card whose route does
  // not exist.
  return (
    <Link to={linkTo} className={className}>
      {content}
    </Link>
  );
}

function AppointmentRow({ appointment }: { appointment: OverviewAppointmentItem }) {
  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);
  return (
    <li>
      <Link
        to="/maintenance/tickets/$ticketId/{-$section}"
        params={{ ticketId: appointment.case_id, section: undefined }}
        className="-mx-1 flex items-center gap-3 rounded-lg px-1 py-2.5 transition-colors hover:bg-accent/60"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold">{appointment.property_address}</div>
          <div className="truncate text-micro text-muted-foreground">
            {appointment.contractor_name} · #{appointment.case_number}
          </div>
        </div>
        <div className="shrink-0 text-right text-micro text-muted-foreground">
          <div>{date}</div>
          <div>{time}</div>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      </Link>
    </li>
  );
}

function ActivityRow({ event }: { event: OverviewActivityItem }) {
  return (
    <li>
      <Link
        to="/maintenance/tickets/$ticketId/{-$section}"
        params={{ ticketId: event.case_id, section: undefined }}
        className="-mx-1 flex items-center gap-3 rounded-lg px-1 py-2.5 transition-colors hover:bg-accent/60"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold">
            #{event.case_number} · {event.case_title}
          </div>
          <div className="truncate text-micro text-muted-foreground">
            {titleCase(event.event_type)}
          </div>
        </div>
        <span className="shrink-0 text-micro text-muted-foreground">
          {formatRelative(event.occurred_at)}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      </Link>
    </li>
  );
}
