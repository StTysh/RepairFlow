import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  ChevronDown,
  Copy,
  Mail,
  MapPin,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Phone,
  Share2,
  Sparkles,
} from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill, PriorityBadge } from "@/components/fixi/Badge";
import { agentTimeline, caseDetails, messages, propertyHistory } from "@/lib/fixi-data";
import { cn } from "@/lib/utils";
import ceilingStain from "@/assets/ceiling-stain.jpg";
import ceilingDamp from "@/assets/ceiling-damp.jpg";
import houseExterior from "@/assets/house-exterior.jpg";
import roofFlashing from "@/assets/roof-flashing.jpg";

const sections = ["summary", "timeline", "messages"] as const;
type Section = (typeof sections)[number];

export const Route = createFileRoute("/maintenance/tickets/$ticketId/{-$section}")({
  loader: ({ params }) => {
    if (params.ticketId !== "1042") throw notFound();
    if (params.section && !sections.includes(params.section as Section)) throw notFound();
    return { section: (params.section as Section | undefined) ?? null };
  },
  head: ({ loaderData }) => {
    const title = loaderData
      ? `#1042 – Roof leak${loaderData.section ? ` · ${cap(loaderData.section)}` : ""} — Fixi`
      : "Ticket not found — Fixi";
    return {
      meta: [
        { title },
        {
          name: "description",
          content:
            "Case details for the roof leak at 14 King Street, Walthamstow: agent timeline, latest messages and property history.",
        },
        { property: "og:title", content: title },
        {
          property: "og:description",
          content: "Case details, AI agent timeline and latest messages for ticket #1042.",
        },
      ],
    };
  },
  component: CasePage,
});

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function CasePage() {
  const { section } = Route.useLoaderData();
  const show = (s: Section) => section === null || section === s;
  const c = caseDetails;

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
            <PriorityBadge priority={c.priority} />
            <h1 className="mt-2 text-2xl font-bold tracking-tight">
              #{c.id} – {c.issue}
            </h1>
            <div className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" /> {c.address}
              <Copy className="ml-1 h-3.5 w-3.5 cursor-pointer hover:text-foreground" />
            </div>
          </div>
          <button className="flex h-9 items-center gap-2 rounded-lg bg-status-blue px-3.5 text-sm font-medium text-status-blue-foreground">
            {c.status} <ChevronDown className="h-4 w-4" />
          </button>
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

        <Card className="mt-5 px-8 py-5">
          <ol className="flex items-start">
            {c.steps.map((s, i) => (
              <li key={s.label} className="relative flex flex-1 flex-col items-center text-center">
                {i < c.steps.length - 1 && (
                  <span
                    className={cn(
                      "absolute left-1/2 top-2.5 h-0.5 w-full",
                      s.state === "done" ? "bg-timeline-done" : "bg-timeline-future",
                    )}
                  />
                )}
                <StepDot state={s.state} />
                <div
                  className={cn(
                    "mt-2 text-xs font-medium",
                    s.state === "future" ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {s.label}
                </div>
                {s.time && <div className="text-[11px] text-muted-foreground">{s.time}</div>}
              </li>
            ))}
          </ol>
        </Card>

        <div className="mt-5 flex items-center gap-1.5">
          <SectionLink section={undefined} active={section === null}>
            All
          </SectionLink>
          <SectionLink section="summary" active={section === "summary"}>
            Summary
          </SectionLink>
          <SectionLink section="timeline" active={section === "timeline"}>
            Timeline
          </SectionLink>
          <SectionLink section="messages" active={section === "messages"}>
            Messages
          </SectionLink>
        </div>

        <div
          className={cn("mt-3 grid gap-4", section === null ? "xl:grid-cols-3" : "xl:grid-cols-1")}
        >
          {show("summary") && <SummaryColumn />}
          {show("timeline") && <TimelineColumn />}
          {show("messages") && <MessagesColumn />}
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
  section,
  active,
  children,
}: {
  section?: Section | undefined;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      to="/maintenance/tickets/$ticketId/{-$section}"
      params={{ ticketId: "1042", section }}
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

function StepDot({ state }: { state: "done" | "current" | "future" }) {
  if (state === "done")
    return (
      <span className="relative z-10 flex h-5 w-5 items-center justify-center rounded-full bg-timeline-done text-primary-foreground">
        <Check className="h-3 w-3" strokeWidth={3} />
      </span>
    );
  if (state === "current")
    return (
      <span className="relative z-10 flex h-5 w-5 items-center justify-center rounded-full border-2 border-timeline-current bg-card">
        <span className="h-2 w-2 rounded-full bg-timeline-current" />
      </span>
    );
  return (
    <span className="relative z-10 h-5 w-5 rounded-full border-2 border-timeline-future bg-card" />
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

function Avatar({ initials, tone }: { initials: string; tone: "gray" | "green" | "purple" }) {
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
      {initials}
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

function OutlineButton({ children }: { children: React.ReactNode }) {
  return (
    <button className="h-8 rounded-lg border border-border bg-card px-3 text-xs font-medium shadow-card hover:bg-accent">
      {children}
    </button>
  );
}

function SummaryColumn() {
  const c = caseDetails;
  return (
    <Card className="p-5">
      <SectionHeader title="Case overview" />
      <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{c.summary}</p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {[ceilingStain, houseExterior, ceilingDamp].map((src, i) => (
          <img
            key={i}
            src={src}
            alt=""
            loading="lazy"
            width={912}
            height={736}
            className="aspect-[4/3] w-full rounded-lg object-cover"
          />
        ))}
      </div>

      <div className="mt-5 border-t border-border pt-4">
        <Label>Tenant</Label>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar initials={c.tenant.initials} tone="gray" />
            <div className="leading-tight">
              <div className="text-[13px] font-medium">{c.tenant.name}</div>
              <div className="text-xs text-muted-foreground">{c.tenant.phone}</div>
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
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar initials={c.contractor.initials} tone="green" />
            <div className="leading-tight">
              <div className="text-[13px] font-medium">{c.contractor.name}</div>
              <div className="text-xs text-muted-foreground">{c.contractor.role}</div>
              <div className="text-xs text-muted-foreground">{c.contractor.phone}</div>
            </div>
          </div>
          <OutlineButton>View profile</OutlineButton>
        </div>
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Next appointment</Label>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
              <Calendar className="h-4 w-4" />
            </div>
            <div className="leading-tight">
              <div className="text-[13px] font-medium">{c.appointment.date}</div>
              <div className="text-xs text-muted-foreground">{c.appointment.time}</div>
            </div>
          </div>
          <OutlineButton>Reschedule</OutlineButton>
        </div>
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Label>Property history</Label>
        <ul className="mt-2 divide-y divide-border rounded-lg border border-border">
          {propertyHistory.slice(0, 4).map((h) => (
            <li key={h.date} className="flex items-center justify-between px-3 py-2 text-xs">
              <span className="w-20 text-muted-foreground">{h.date}</span>
              <span className="flex-1 font-medium">{h.issue}</span>
              <Pill tone="green">{h.state}</Pill>
            </li>
          ))}
        </ul>
        <Link
          to="/properties/14-king-street/history"
          className="mt-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-card text-xs font-medium shadow-card hover:bg-accent"
        >
          View full property history <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </Card>
  );
}

function TimelineColumn() {
  return (
    <Card className="p-5">
      <SectionHeader
        title="Agent timeline"
        subtitle="What the AI agent has done and what's next."
      />
      <ol className="mt-4">
        {agentTimeline.map((item, i) => {
          const last = i === agentTimeline.length - 1;
          return (
            <li key={item.title} className="relative flex gap-3 pb-5 last:pb-0">
              {!last && (
                <span
                  className={cn(
                    "absolute left-[9px] top-5 h-full w-0.5",
                    item.state === "done" ? "bg-timeline-done" : "bg-timeline-future",
                  )}
                />
              )}
              <StepDot state={item.state} />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div
                    className={cn(
                      "text-[13px] font-semibold",
                      item.state === "future" && "text-muted-foreground",
                    )}
                  >
                    {item.title}
                  </div>
                  {item.time ? (
                    <span className="shrink-0 text-[11px] text-muted-foreground">{item.time}</span>
                  ) : (
                    <Pill tone={item.state === "current" ? "blue" : "gray"} className="text-[10px]">
                      {item.state === "current" ? "Current" : "Upcoming"}
                    </Pill>
                  )}
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{item.body}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function MessagesColumn() {
  return (
    <Card className="flex flex-col p-5">
      <SectionHeader
        title="Latest incoming messages"
        subtitle="Messages, calls and updates from all parties."
        action={
          <button className="text-xs font-medium text-primary hover:underline">View all</button>
        }
      />
      <ul className="mt-4 divide-y divide-border">
        {messages.map((m, i) => {
          const isAI = m.type === "AI Agent";
          return (
            <li key={i} className="flex gap-3 py-3 first:pt-0">
              {isAI ? (
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-status-purple text-status-purple-foreground">
                  <Sparkles className="h-4 w-4" />
                </div>
              ) : (
                <Avatar
                  initials={m.type === "Tenant" ? "JD" : "AR"}
                  tone={m.type === "Tenant" ? "gray" : "green"}
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-[13px] font-semibold">{m.sender}</span>
                    <Pill
                      tone={isAI ? "purple" : m.type === "Tenant" ? "gray" : "green"}
                      className="ml-2 text-[10px]"
                    >
                      {m.type}
                    </Pill>
                  </div>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{m.time}</span>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{m.text}</p>
                {m.attachments === "tenant" && (
                  <div className="mt-2 flex gap-1.5">
                    {[ceilingStain, ceilingDamp].map((src, j) => (
                      <img
                        key={j}
                        src={src}
                        alt=""
                        loading="lazy"
                        width={912}
                        height={736}
                        className="h-14 w-20 rounded-md object-cover"
                      />
                    ))}
                  </div>
                )}
                {m.attachments === "contractor" && (
                  <div className="mt-2 flex gap-1.5">
                    <img
                      src={roofFlashing}
                      alt=""
                      loading="lazy"
                      width={912}
                      height={736}
                      className="h-14 w-20 rounded-md object-cover"
                    />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto rounded-xl bg-primary-soft p-4">
        <div className="flex gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="text-[13px] font-semibold">Need full history?</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              See all previous issues, repairs and documents for this property.
            </p>
          </div>
        </div>
        <Link
          to="/properties/14-king-street/history"
          className="mt-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-card text-xs font-medium shadow-card hover:bg-accent"
        >
          View full history <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </Card>
  );
}
