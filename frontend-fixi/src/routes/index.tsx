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
import {
  useOverview,
  type NeedsAttentionItem,
  type OverviewActivityItem,
  type OverviewAppointmentItem,
} from "@/hooks/use-analytics";
import { formatDateRange, formatRelative } from "@/lib/format";
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

const NEEDS_ATTENTION_ICON: Record<NeedsAttentionItem["kind"], LucideIcon> = {
  AWAITING_APPROVAL: MessageCircle,
  ESCALATED: AlertTriangle,
  OVERDUE_FOLLOW_UP: Clock3,
};

const NEEDS_ATTENTION_TONE_CLASS: Record<NeedsAttentionItem["kind"], string> = {
  AWAITING_APPROVAL: "bg-status-amber text-status-amber-foreground",
  ESCALATED: "bg-status-red text-status-red-foreground",
  OVERDUE_FOLLOW_UP: "bg-status-orange text-status-orange-foreground",
};

const NEEDS_ATTENTION_LABEL: Record<NeedsAttentionItem["kind"], string> = {
  AWAITING_APPROVAL: "Awaiting approval",
  ESCALATED: "Escalated",
  OVERDUE_FOLLOW_UP: "Overdue follow-up",
};

function OverviewPage() {
  const overview = useOverview();
  const data = overview.data;

  function retryOverview() {
    void overview.refetch();
  }

  const needsAttention = data?.needs_attention ?? [];
  const upcoming = data?.upcoming_appointments ?? [];
  const activity = data?.recent_activity ?? [];

  // "Open cases" isn't guaranteed as its own field on the contract -- if the
  // backend sends one directly, use it; otherwise derive it from the
  // per-status breakdown (the 3 non-terminal CaseStatus values), and only
  // fall back to "--" if neither is present at all. Never a client-side
  // guess beyond summing real counts the backend actually returned.
  const openCases =
    data?.open_case_count ??
    (data?.case_counts_by_status
      ? (data.case_counts_by_status.ACTIVE ?? 0) +
        (data.case_counts_by_status.AWAITING_CONFIRMATION ?? 0) +
        (data.case_counts_by_status.ESCALATED ?? 0)
      : undefined);

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
                  <h2 className="text-sm font-semibold">Needs attention</h2>
                  {!overview.isLoading && needsAttention.length > 0 && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[11px] font-bold text-destructive-foreground">
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
                        const Icon = NEEDS_ATTENTION_ICON[item.kind];
                        return (
                          <li key={item.id}>
                            <Link
                              to="/maintenance/tickets/$ticketId/{-$section}"
                              params={{ ticketId: item.case_id, section: undefined }}
                              className="-mx-1 flex items-center gap-3 rounded-lg px-1 py-2.5 transition-colors hover:bg-accent/60"
                            >
                              <span
                                className={cn(
                                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                                  NEEDS_ATTENTION_TONE_CLASS[item.kind],
                                )}
                              >
                                <Icon className="h-4 w-4" />
                              </span>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="truncate text-xs font-semibold">
                                    #{item.case_number} · {item.case_title}
                                  </span>
                                  <span className="shrink-0 text-[10px] font-medium text-muted-foreground">
                                    {NEEDS_ATTENTION_LABEL[item.kind]}
                                  </span>
                                </div>
                                <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                                  {item.message}
                                </p>
                              </div>
                              <span className="shrink-0 text-[10px] text-muted-foreground">
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
                  <h2 className="text-sm font-semibold">Upcoming appointments</h2>
                  <Link
                    to="/maintenance"
                    className="text-[11px] font-medium text-primary hover:underline"
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
                <h2 className="text-sm font-semibold">Recent activity</h2>
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
                        <ActivityRow key={event.id} event={event} />
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
        <div className="text-xl font-bold tracking-tight">{value ?? "—"}</div>
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
          <div className="truncate text-[11px] text-muted-foreground">
            {appointment.contractor_name} · #{appointment.case_number}
          </div>
        </div>
        <div className="shrink-0 text-right text-[11px] text-muted-foreground">
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
          <div className="truncate text-[11px] text-muted-foreground">{event.display_title}</div>
        </div>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {formatRelative(event.occurred_at)}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      </Link>
    </li>
  );
}
